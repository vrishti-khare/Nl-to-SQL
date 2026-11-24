"""
=============================================================
Wargame AI SQL Assistant -- Main Entry Point
=============================================================
Full pipeline:
  1. User asks a natural language question
  2. RAG retrieves relevant schema columns (pgvector)
  3. SQLCoder (via Ollama) generates SQL
  4. SQL executes against PostgreSQL (with retry loop)
  5. Mistral (via Ollama) classifies output type
  6. Mistral (via Ollama) synthesizes a natural language answer

Requirements:
  - PostgreSQL 17 with pgvector running on localhost:5432
  - Ollama running on localhost:11434 with sqlcoder + mistral
  - Embeddings populated (run embed_schema.py first)

Usage:
    python main.py
=============================================================
"""

import time
import json
import urllib.request
import urllib.error
import psycopg2
from config import DB_CONFIG, OLLAMA_BASE_URL, SQL_MODEL, ANSWER_MODEL
from vector_search import search_schema
from generate_sql import build_sql_prompt
from output_renderer import render_output


def call_ollama(model, prompt, temperature=0.0):
    """
    Call Ollama's REST API to generate text.

    Args:
        model: Name of the Ollama model (e.g. 'sqlcoder', 'mistral')
        prompt: The full prompt string
        temperature: 0.0 for deterministic SQL, 0.3 for creative answers

    Returns:
        Generated text string, or None on python error.
    """
    url = "%s/api/generate" % OLLAMA_BASE_URL
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 1000,
        }
    }

    try:
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=900) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get("response", "").strip()
    except urllib.error.URLError as e:
        print("  [ERROR] Cannot connect to Ollama at %s: %s" % (OLLAMA_BASE_URL, str(e)))
        print("          Make sure Ollama is running: ollama serve")
        return None
    except Exception as e:
        print("  [ERROR] Ollama request failed: %s" % str(e))
        return None


def extract_sql(raw_response):
    """
    Clean up LLM output to extract just the SQL query.
    Removes markdown fences, explanatory text, and fixes known
    SQLCoder formatting quirks.
    """
    import re

    if not raw_response:
        return None

    sql = raw_response.strip()

    # Remove markdown code fences
    if sql.startswith("```sql"):
        sql = sql[6:]
    elif sql.startswith("```"):
        sql = sql[3:]
    if sql.endswith("```"):
        sql = sql[:-3]

    sql = sql.strip()
    sql = sql.strip("`")  # Remove single backticks
    sql = sql.strip('"')  # Remove double quotes wrapping
    sql = sql.strip("'")  # Remove single quotes wrapping
    sql = sql.strip(";")  # Remove stray outer semicolons
    sql = sql.strip()

    # ---- Phase 1: Fix split and squashed keywords ----
    sql = re.sub(r'\bOR\s+DER\s+BY\b', 'ORDER BY', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bGR\s+OUP\s+BY\b', 'GROUP BY', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bL\s+AS\s+T\b', 'LAST', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bLI\s+MIT\b', 'LIMIT', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bDE\s+SC\b', 'DESC', sql, flags=re.IGNORECASE)
    
    # Advanced squashing fixes
    sql = re.sub(r'(?i)ORDERBY', ' ORDER BY ', sql)
    sql = re.sub(r'(?i)GROUPBY', ' GROUP BY ', sql)
    sql = re.sub(r'(?i)NULLSLAST', ' NULLS LAST ', sql)
    
    # Split numbers attached directly to keywords (e.g. 20ORDERBY)
    sql = re.sub(r'(\d)(ORDER BY|LIMIT|DESC|ASC|GROUP BY)', r'\1 \2', sql, flags=re.IGNORECASE)

    # ---- Phase 2: Fix squashed text (brute force) ----
    # Because regex boundaries fail when text is entirely squashed, we use
    # safe case-sensitive replacements for uppercase SQL keywords.
    uppercase_keywords = [
        'SELECT', 'FROM', 'JOIN', 'WHERE', 'AND', 'GROUP BY', 'ORDER BY',
        'LIMIT', 'DESC', 'ASC', 'HAVING', 'NULLS LAST'
    ]
    for kw in uppercase_keywords:
        sql = sql.replace(kw, ' ' + kw + ' ')

    # Sometimes SQLCoder lowercases 'on' and squashes it (e.g. forceonplatform_profile)
    # Let's brute force the common table boundaries
    sql = sql.replace('forceon', 'force on ')
    sql = sql.replace('profileon', 'profile on ')
    sql = sql.replace('logon', 'log on ')
    sql = sql.replace('gameon', 'game on ')
    sql = sql.replace('logON', 'log ON ')
    sql = sql.replace('gameON', 'game ON ')
    
    sql = sql.replace('ONplatform', 'ON platform')
    sql = sql.replace('ONmain', 'ON main')
    sql = sql.replace('ONforce', 'ON force')

    sql = sql.replace('FROMplatform', 'FROM platform')
    sql = sql.replace('FROMmain', 'FROM main')
    sql = sql.replace('FROMforce', 'FROM force')

    sql = sql.replace('JOINplatform', 'JOIN platform')
    sql = sql.replace('JOINmain', 'JOIN main')
    sql = sql.replace('JOINforce', 'JOIN force')

    sql = sql.replace('WHEREplatform', 'WHERE platform')
    sql = sql.replace('WHEREmain', 'WHERE main')
    sql = sql.replace('WHEREforce', 'WHERE force')

    sql = sql.replace('ANDplatform', 'AND platform')
    sql = sql.replace('ANDmain', 'AND main')
    sql = sql.replace('ANDforce', 'AND force')

    sql = sql.replace("='submarine'AND", "='submarine' AND ")

    # ---- Phase 3: Clean up ----
    sql = re.sub(r'\s+', ' ', sql).strip()

    # Ensure it ends with a semicolon
    if not sql.endswith(";"):
        sql = sql + ";"

    # ---- Phase 4: Pre-Execution Sanitization ----
    # Fix force_id = 'Red' -> force_name ILIKE '%Red%'
    sql = re.sub(r"force_id\s*=\s*'([^']+)'", r"force_name ILIKE '%\g<1>%'", sql, flags=re.IGNORECASE)
    # Fix force_name = 'Red' -> force_name ILIKE '%Red%'
    sql = re.sub(r"force_name\s*=\s*'([^']+)'", r"force_name ILIKE '%\g<1>%'", sql, flags=re.IGNORECASE)
    # Fix zone_boundaries.zone_id -> zone_boundaries.zone_name
    sql = re.sub(r"zone_boundaries\.zone_id", 'zone_boundaries.zone_name', sql, flags=re.IGNORECASE)

    # Fix unterminated string quotes (e.g., ILIKE '%Blue%; -> ILIKE '%Blue%';)
    sql = sql.replace("%;", "%';")

    # Force SELECT DISTINCT on raw lists to prevent millions of duplicate time-series rows
    sql = re.sub(r"(?i)^SELECT\s+(?!DISTINCT|COUNT|SUM|MIN|MAX|AVG)", "SELECT DISTINCT ", sql)

    # Strip hallucinated WHERE conditions the 7B model invents (weapon_status, radar_status, etc.)
    hallucinated_cols = r"(?:weapon_status|radar_status|sonar_status|engine_status|communication_status|operational_status|hull_integrity_pct)"
    # Case: AND table.col = 'value'
    sql = re.sub(r"(?i)\s+AND\s+[a-zA-Z_]*\.?" + hallucinated_cols + r"\s*(?:=|>|<|>=|<=|!=)\s*'[^']*'", "", sql)
    # Case: AND table.col > 0
    sql = re.sub(r"(?i)\s+AND\s+[a-zA-Z_]*\.?" + hallucinated_cols + r"\s*(?:=|>|<|>=|<=|!=)\s*\d+", "", sql)
    # Case: WHERE table.col = 'value' AND ... (strip the leading WHERE condition, keep AND)
    sql = re.sub(r"(?i)\s+WHERE\s+[a-zA-Z_]*\.?" + hallucinated_cols + r"\s*(?:=|>|<|>=|<=|!=)\s*'[^']*'\s+AND\s+", " WHERE ", sql)
    # Strip hallucinated depth_meters > 0 (LLM uses this as a proxy for "is submarine" which is wrong)
    sql = re.sub(r"(?i)\s+AND\s+[a-zA-Z_]*\.?depth_meters\s*(?:>|>=)\s*0", "", sql)
    # Strip hallucinated altitude_meters > 0 (LLM uses this as a proxy for "is aircraft" which is wrong)
    sql = re.sub(r"(?i)\s+AND\s+[a-zA-Z_]*\.?altitude_meters\s*(?:>|>=)\s*0", "", sql)

    # Fix common column name typos the 7B model makes
    typo_fixes = {
        'latude': 'latitude', 'latitide': 'latitude', 'lat_itude': 'latitude',
        'longtiude': 'longitude', 'longtitude': 'longitude', 'longitdue': 'longitude',
        'platfrom': 'platform', 'platofrm': 'platform',
        'force_naem': 'force_name', 'froce_name': 'force_name',
        'platfrom_name': 'platform_name', 'plaform_name': 'platform_name',
        'timestmap': 'timestamp', 'timestampe': 'timestamp',
    }
    for typo, correct in typo_fixes.items():
        sql = re.sub(r'\b' + typo + r'\b', correct, sql, flags=re.IGNORECASE)

    # Strip query_log references — the LLM sometimes JOINs query_log to "search" for the answer
    # This is always wrong. Remove the entire JOIN and any WHERE clause referencing query_log.
    sql = re.sub(r"(?i)\s+JOIN\s+query_log\s+ON\s+[^W]+?(?=WHERE|GROUP|ORDER|LIMIT|;|$)", " ", sql)
    sql = re.sub(r"(?i)\s+AND\s+query_log\.\w+\s*(?:ILIKE|=|!=|LIKE)\s*'[^']*'", "", sql)
    sql = re.sub(r"(?i)\s+WHERE\s+query_log\.\w+\s*(?:ILIKE|=|!=|LIKE)\s*'[^']*'\s+AND\s+", " WHERE ", sql)
    sql = re.sub(r"(?i)\s+WHERE\s+query_log\.\w+\s*(?:ILIKE|=|!=|LIKE)\s*'[^']*'\s*", " ", sql)

    # Fix "game_id = 'game1'" or scenario_name ILIKE '%Game1%' -> game_id = 1
    # The user says "game1" meaning game_id=1, but the LLM sometimes treats it as a string search
    game_ref_match = re.search(r"(?i)scenario_(?:name|objective)\s*ILIKE\s*'%+[Gg]ame\s*(\d+)%+'", sql)
    if game_ref_match:
        game_num = game_ref_match.group(1)
        sql = re.sub(re.escape(game_ref_match.group(0)), "game_id = %s" % game_num, sql)

    # Fix to_timestamp() wrapping on columns that are already TIMESTAMP type.
    # LLM writes to_timestamp(real_timestamp/1000) which crashes because you can't divide timestamp by int.
    # Pattern 1: to_timestamp(col/1000) -> col  (strip the entire wrapper + division)
    timestamp_cols = r"(?:[a-zA-Z_]*\.?(?:real_timestamp|detection_lost_timestamp|game_start_real_time))"
    sql = re.sub(r"(?i)to_timestamp\(\s*" + timestamp_cols + r"\s*/\s*\d+\s*\)", lambda m: re.search(timestamp_cols, m.group(0), re.IGNORECASE).group(0), sql)
    # Pattern 2: to_timestamp(col) -> col  (redundant wrapper, col is already timestamp)
    sql = re.sub(r"(?i)to_timestamp\(\s*(" + timestamp_cols + r")\s*\)", r"\1", sql)
    # Pattern 3: to_date(to_char(col, fmt), fmt) = to_date('2026-06-04', 'DD-MM-YYYY') -> col::date = '2026-06-04'
    sql = re.sub(r"(?i)to_date\s*\(\s*to_char\s*\(\s*" + timestamp_cols + r"\s*,\s*'[^']*'\s*\)\s*,\s*'[^']*'\s*\)\s*=\s*to_date\s*\(\s*'(\d{4}-\d{2}-\d{2})'\s*,\s*'[^']*'\s*\)", lambda m: "%s::date = '%s'" % (re.search(timestamp_cols, m.group(0), re.IGNORECASE).group(0), re.search(r"'(\d{4}-\d{2}-\d{2})'", m.group(0)).group(1)), sql)

    return sql


def auto_fix_missing_join(sql, error_message):
    """
    Programmatically fix 'missing FROM-clause entry for table X' errors.

    SQLCoder on limited hardware repeatedly fails to self-correct this error.
    Instead of wasting 10 minutes per retry, we fix it ourselves using our
    knowledge of the database schema's foreign key relationships.

    Args:
        sql: The SQL that failed.
        error_message: The PostgreSQL error message.

    Returns:
        Fixed SQL string, or None if we can't fix it.
    """
    import re

    # Check if this is a "missing FROM-clause" error
    match = re.search(r'missing FROM-clause entry for table "(\w+)"', error_message)
    if not match:
        return None

    missing_table = match.group(1)

    # Known join relationships from our schema
    # Format: missing_table -> (join_to_table, join_condition)
    join_map = {
        'platform_telemetry_log': [
            ('platform_profile', 'platform_telemetry_log.game_id = platform_profile.game_id AND platform_telemetry_log.platform_id = platform_profile.platform_id'),
            ('main_consolidated_log', 'platform_telemetry_log.game_id = main_consolidated_log.game_id AND platform_telemetry_log.platform_id = main_consolidated_log.platform_id AND platform_telemetry_log.clock_tick = main_consolidated_log.clock_tick'),
        ],
        'platform_profile': [
            ('force', 'platform_profile.game_id = force.game_id AND platform_profile.force_id = force.force_id'),
            ('platform_telemetry_log', 'platform_profile.game_id = platform_telemetry_log.game_id AND platform_profile.platform_id = platform_telemetry_log.platform_id'),
            ('main_consolidated_log', 'platform_profile.game_id = main_consolidated_log.game_id AND platform_profile.platform_id = main_consolidated_log.platform_id'),
            ('tactical_actions', 'platform_profile.game_id = tactical_actions.game_id AND platform_profile.platform_id = tactical_actions.platform_id'),
            ('weapon_employment_log', 'platform_profile.game_id = weapon_employment_log.game_id AND platform_profile.platform_id = weapon_employment_log.platform_id'),
            ('detection_log', 'platform_profile.game_id = detection_log.game_id AND platform_profile.platform_id = detection_log.detecting_platform_id'),
        ],
        'main_consolidated_log': [
            ('platform_profile', 'main_consolidated_log.game_id = platform_profile.game_id AND main_consolidated_log.platform_id = platform_profile.platform_id'),
            ('platform_telemetry_log', 'main_consolidated_log.game_id = platform_telemetry_log.game_id AND main_consolidated_log.platform_id = platform_telemetry_log.platform_id AND main_consolidated_log.clock_tick = platform_telemetry_log.clock_tick'),
        ],
        'force': [
            ('game', 'force.game_id = game.game_id'),
            ('platform_profile', 'force.game_id = platform_profile.game_id AND force.force_id = platform_profile.force_id'),
            ('messages', 'force.game_id = messages.game_id AND force.force_id = messages.force_id'),
        ],
        'tactical_actions': [
            ('platform_profile', 'tactical_actions.game_id = platform_profile.game_id AND tactical_actions.platform_id = platform_profile.platform_id'),
        ],
        'weapon_employment_log': [
            ('platform_profile', 'weapon_employment_log.game_id = platform_profile.game_id AND weapon_employment_log.platform_id = platform_profile.platform_id'),
        ],
        'detection_log': [
            ('platform_profile', 'detection_log.game_id = platform_profile.game_id AND detection_log.detecting_platform_id = platform_profile.platform_id'),
        ],
        'messages': [
            ('force', 'messages.game_id = force.game_id AND messages.force_id = force.force_id'),
        ],
        'game': [
            ('force', 'game.game_id = force.game_id'),
        ],
    }

    if missing_table not in join_map:
        return None

    # Find which tables are already in the SQL (in the FROM/JOIN clauses)
    tables_in_sql = re.findall(r'(?:FROM|JOIN)\s+(\w+)', sql, re.IGNORECASE)

    # Try to find a join partner that's already in the query
    for join_to, condition in join_map[missing_table]:
        if join_to in tables_in_sql:
            # Insert the JOIN right before WHERE (or at the end if no WHERE)
            join_clause = " JOIN %s ON %s" % (missing_table, condition)

            if re.search(r'\bWHERE\b', sql, re.IGNORECASE):
                fixed = re.sub(r'\bWHERE\b', join_clause + ' WHERE', sql, count=1, flags=re.IGNORECASE)
            elif re.search(r'\bORDER\b', sql, re.IGNORECASE):
                fixed = re.sub(r'\bORDER\b', join_clause + ' ORDER', sql, count=1, flags=re.IGNORECASE)
            elif re.search(r'\bGROUP\b', sql, re.IGNORECASE):
                fixed = re.sub(r'\bGROUP\b', join_clause + ' GROUP', sql, count=1, flags=re.IGNORECASE)
            else:
                fixed = sql.rstrip(';') + join_clause + ';'

            return fixed

    return None


def auto_fix_type_mismatch(sql, error_message):
    """
    Programmatically fix 'operator does not exist: character varying = integer' errors.
    
    SQLCoder frequently tries to JOIN current_zone (which is a string like 'Zone Alpha')
    to zone_id (which is an integer) instead of joining to zone_name.
    """
    import re
    if "operator does not exist: character varying = integer" in error_message:
        # Check if the bad join is current_zone = zone_id
        if "current_zone" in sql and "zone_id" in sql:
            # Replace zone_id with zone_name in the JOIN condition
            fixed = re.sub(r'zone_boundaries\.zone_id', 'zone_boundaries.zone_name', sql, flags=re.IGNORECASE)
            # Make sure we didn't accidentally replace a valid SELECT zone_id
            if fixed != sql:
                return fixed
    return None


def auto_fix_wrong_column_table(sql, error_message):
    """
    Programmatically fix 'column X.Y does not exist' errors.
    
    SQLCoder sometimes hallucinates the location of a column (e.g. asking for 
    platform_telemetry_log.platform_name, when platform_name is in platform_profile).
    Also catches wrong column names using PostgreSQL HINT suggestions.
    """
    import re
    match = re.search(r'column (\w+)\.(\w+) does not exist', error_message)
    if not match:
        return None
        
    wrong_table = match.group(1)
    column_name = match.group(2)
    
    # --- Strategy 1: Check if PostgreSQL gave us a HINT ---
    # PostgreSQL formats hints as: Perhaps you meant to reference the column "table_name"."col_name"
    # OR: Perhaps you meant to reference the column "table_name.col_name"
    hint_match = re.search(r'HINT:\s+Perhaps you meant to reference the column "([^"]+)"(?:\."([^"]+)")?', error_message)
    if hint_match:
        if hint_match.group(2):
            # Format: "table"."column"
            hint_table = hint_match.group(1)
            hint_col = hint_match.group(2)
        elif '.' in hint_match.group(1):
            # Format: "table.column" (single quoted)
            parts = hint_match.group(1).split('.', 1)
            hint_table = parts[0]
            hint_col = parts[1]
        else:
            # Just a column name
            hint_table = wrong_table
            hint_col = hint_match.group(1)

        # Replace the bad column name with the HINT suggestion
        bad_ref = "%s.%s" % (wrong_table, column_name)
        good_ref = "%s.%s" % (wrong_table, hint_col)
        fixed = sql.replace(bad_ref, good_ref)
        if fixed != sql:
            return fixed
        # Also try without table prefix (unqualified column)
        fixed = sql.replace(column_name, hint_col)
        if fixed != sql:
            return fixed

    # --- Strategy 2: Known column-to-table map ---
    # Map of commonly hallucinated columns to their correct tables
    column_map = {
        'platform_name': 'platform_profile',
        'platform_type': 'platform_profile',
        'force_name': 'force',
        'commander_name': 'force',
        'weapon_load': 'platform_profile',
        'max_speed_knots': 'platform_profile',
        'max_crew': 'platform_profile',
        'radar_range_km': 'platform_profile',
        'sonar_range_km': 'platform_profile',
        'fuel_type': 'platform_profile',
        'max_fuel_capacity': 'platform_profile',
        'total_platforms': 'force',
        'scenario_name': 'game',
        'total_forces': 'game',
    }
    
    if column_name in column_map:
        correct_table = column_map[column_name]
        if wrong_table != correct_table:
            bad_ref = "%s.%s" % (wrong_table, column_name)
            good_ref = "%s.%s" % (correct_table, column_name)
            fixed = re.sub(re.escape(bad_ref), good_ref, sql, flags=re.IGNORECASE)
            if fixed != sql:
                return fixed

    # --- Strategy 3: Column exists in main_consolidated_log ---
    # Many columns the LLM looks for on platform_telemetry_log or platform_profile
    # also exist in main_consolidated_log
    mcl_columns = {
        'platform_name', 'platform_type', 'force_name', 'latitude', 'longitude',
        'speed_knots', 'course_deg', 'altitude_meters', 'depth_meters',
        'fuel_level', 'fuel_consumed_interval', 'radar_status', 'sonar_status',
        'hull_integrity_pct', 'current_zone', 'visibility_km', 'sea_state',
        'operational_status', 'clock_tick', 'real_timestamp'
    }
    if column_name in mcl_columns and wrong_table != 'main_consolidated_log':
        # Check if main_consolidated_log is already in the query
        if 'main_consolidated_log' in sql:
            bad_ref = "%s.%s" % (wrong_table, column_name)
            good_ref = "main_consolidated_log.%s" % column_name
            fixed = re.sub(re.escape(bad_ref), good_ref, sql, flags=re.IGNORECASE)
            if fixed != sql:
                return fixed
                
    return None


def auto_fix_bad_alias(sql, error_message):
    """
    Fix errors where LLM joins a table with an alias (e.g. platform_profile AS pp)
    but then selects a column using a hallucinated alias (e.g. pt.weapon_load).
    This causes 'missing FROM-clause entry for table "pt"'.
    """
    import re
    match = re.search(r'missing FROM-clause entry for table "(\w+)"', error_message)
    if not match: return None
    missing_alias = match.group(1)
    
    if len(missing_alias) > 3: return None
    
    cols = re.findall(rf'\b{missing_alias}\.(\w+)', sql)
    if not cols: return None
    
    col = cols[0]
    column_map = {
        'weapon_load': 'platform_profile',
        'platform_name': 'platform_profile',
        'max_speed_knots': 'platform_profile',
        'platform_type': 'platform_profile',
        'force_name': 'force',
        'commander_name': 'force',
        'message_content': 'messages'
    }
    
    if col in column_map:
        true_table = column_map[col]
        alias_match = re.search(rf'{true_table}\s+(?:AS\s+)?(\w+)\b', sql, re.IGNORECASE)
        if alias_match:
            true_alias = alias_match.group(1)
            fixed = re.sub(rf'\b{missing_alias}\.', f'{true_alias}.', sql)
            if fixed != sql: return fixed
        else:
            fixed = re.sub(rf'\b{missing_alias}\.', f'{true_table}.', sql)
            if fixed != sql: return fixed
            
    return None


def build_correction_prompt(user_question, bad_sql, error_message, schema_context):
    """
    Build a correction prompt when generated SQL fails execution.
    Sends the bad SQL + PostgreSQL error back to SQLCoder so it can fix itself.

    Args:
        user_question: The original user question.
        bad_sql: The SQL that failed.
        error_message: The PostgreSQL error message.
        schema_context: The RAG-retrieved schema columns.

    Returns:
        Corrected prompt string for SQLCoder.
    """
    from generate_sql import SCHEMA_DDL

    prompt = "### Task\n"
    prompt += "The following SQL query was generated to answer a question, "
    prompt += "but it failed with an error. Fix the SQL.\n\n"
    prompt += "### Original Question\n"
    prompt += "`%s`\n\n" % user_question
    prompt += "### Failed SQL\n"
    prompt += "```sql\n%s\n```\n\n" % bad_sql
    prompt += "### PostgreSQL Error\n"
    prompt += "`%s`\n\n" % error_message
    prompt += "### Database Schema\n"
    prompt += SCHEMA_DDL + "\n\n"
    prompt += "### Relevant Columns\n"
    for row in schema_context:
        table, column, description = row[0], row[1], row[2]
        prompt += "- %s.%s: %s\n" % (table, column, description)
    prompt += "\n### Instructions\n"
    prompt += "- Fix the SQL error based on the error message above.\n"
    prompt += "- CRITICAL: If the error says 'missing FROM-clause entry for table X', you MUST explicitly add 'JOIN X' to your FROM clause, or change your SELECT columns to use the tables already in your FROM clause.\n"
    prompt += "- Return ONLY the corrected SQL query, no explanations.\n"
    prompt += "- Use ONLY tables and columns from the schema.\n\n"
    prompt += "### Corrected SQL\n"

    return prompt


def decide_output_type(user_question):
    """
    Ask Mistral to classify the best output format for the user's question.

    Returns one of: 'text', 'map', 'bar_chart', 'line_chart', 'timeline'
    """
    prompt = (
        "You are a classifier. Based on the user's question about wargame data, "
        "decide the best output format.\n\n"
        "Rules:\n"
        "- If the question asks about locations, positions, or coordinates: respond 'map'\n"
        "- If the question asks about trends over time, fuel changes, or progression: respond 'line_chart'\n"
        "- If the question asks to compare forces, count platforms, or rank items: respond 'bar_chart'\n"
        "- If the question asks about sequence of events, actions over time, or battle timeline: respond 'timeline'\n"
        "- For all other questions (facts, names, descriptions): respond 'text'\n\n"
        "Question: %s\n\n"
        "Respond with ONLY one word: text, map, bar_chart, line_chart, or timeline."
    ) % user_question

    result = call_ollama(ANSWER_MODEL, prompt, temperature=0.0)

    if result:
        # Extract just the classification word from the response
        result_lower = result.strip().lower().rstrip('.')
        valid_types = ['text', 'map', 'bar_chart', 'line_chart', 'timeline']
        for vt in valid_types:
            if vt in result_lower:
                return vt

    return 'text'  # Default fallback


def execute_sql(sql):
    """
    Execute SQL against the wargame database and return results.

    Returns:
        (columns, rows) on success -- columns is a list of names, rows is list of tuples.
        (None, error_message) on failure.
    """
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute(sql)
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                return columns, rows
            else:
                return [], []
    except Exception as e:
        return None, str(e)
    finally:
        if conn:
            conn.close()


def build_answer_prompt(user_question, sql, columns, rows):
    """
    Build a prompt for Mistral to synthesize a natural language answer
    from the SQL query results.
    """
    # Limit output to prevent massive prompts
    max_rows = 20
    truncated = len(rows) > max_rows
    display_rows = rows[:max_rows]

    result_text = ""
    if columns:
        result_text += " | ".join(columns) + "\n"
        result_text += "-" * 40 + "\n"
        for row in display_rows:
            result_text += " | ".join(str(v) for v in row) + "\n"

    if truncated:
        result_text += "... (%d more rows not shown)\n" % (len(rows) - max_rows)

    prompt = (
        "You are a military wargame analyst. The user asked a question "
        "about wargame simulation data.\n\n"
        "User Question: %s\n\n"
        "SQL Query Executed:\n%s\n\n"
        "Query Results:\n%s\n"
        "Provide a clear, concise answer to the user's question based on "
        "the data above. Include specific numbers, platform names, and force "
        "names from the results. If the results are empty, explain that no "
        "matching data was found. Keep the answer under 200 words."
    ) % (user_question, sql, result_text)

    return prompt


def log_query(game_id, user_question, generated_sql, sql_executed,
              execution_time_ms, final_answer, output_type="text", force_id=None):
    """Save the query to the query_log table for audit."""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO query_log
                    (game_id, user_question, generated_sql, sql_executed,
                     execution_time_ms, final_answer, output_type, force_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (game_id, user_question, generated_sql, sql_executed,
                  execution_time_ms, final_answer, output_type, force_id))
            conn.commit()
    except Exception:
        pass  # Don't let logging failures crash the main pipeline
    finally:
        if conn:
            conn.close()


def main():
    print("=" * 60)
    print("  Wargame AI SQL Assistant")
    print("  SQL Model : %s (via Ollama)" % SQL_MODEL)
    print("  Answer Model: %s (via Ollama)" % ANSWER_MODEL)
    print("  Database  : %s" % DB_CONFIG["dbname"])
    print("=" * 60)
    print("\nType your questions about the wargame data.")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            raw_user_input = input("Question: ")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if raw_user_input.strip().lower() in ("exit", "quit"):
            print("Exiting.")
            break

        if not raw_user_input.strip():
            continue


        print("\n  [0/6] Analyzing input for multiple questions...")
        split_prompt = (
            "You are a question splitter for wargame queries. "
            "Split the user input into separate, self-contained questions.\n\n"
            "CRITICAL RULES:\n"
            "- A question and its date/time/location qualifier is ONE question. "
            "Example: 'location of ships at 1:00pm on June 4th' is ONE question, not two.\n"
            "- Only split when there are truly independent questions joined by a period, question mark, or connecting words like 'and also', 'additionally'.\n"
            "- Each split question must be self-contained with all its context (force name, date, time, etc).\n"
            "- When in doubt, keep as ONE question.\n\n"
            "Return ONLY a valid JSON list of strings, no markdown, no explanation.\n\n"
            "Examples:\n"
            "Input: 'Where are Red ships on June 4th at 5pm?' -> [\"Where are Red ships on June 4th at 5pm?\"]\n"
            "Input: 'List Blue submarines. What is the weapon load of Red ships?' -> [\"List Blue submarines.\", \"What is the weapon load of Red ships?\"]\n"
            "Input: 'Give me location of green force platforms at 1:00pm on 4th june 2026' -> [\"Give me location of green force platforms at 1:00pm on 4th june 2026\"]\n\n"
            "Input: %s"
        ) % raw_user_input

        split_result = call_ollama(ANSWER_MODEL, split_prompt, temperature=0.0)
        questions = [raw_user_input]
        if split_result:
            try:
                import json
                cleaned = split_result.strip()
                if cleaned.startswith("```json"): cleaned = cleaned[7:]
                if cleaned.startswith("```"): cleaned = cleaned[3:]
                if cleaned.endswith("```"): cleaned = cleaned[:-3]
                parsed = json.loads(cleaned.strip())
                if isinstance(parsed, list) and len(parsed) > 0:
                    questions = parsed
            except Exception:
                pass

        if len(questions) > 1:
            print("  Detected %d distinct questions. Processing sequentially..." % len(questions))

        for q_idx, user_question in enumerate(questions):
            if len(questions) > 1:
                print("\n" + "=" * 60)
                print("--- Processing Question %d/%d: %s ---" % (q_idx+1, len(questions), user_question))
                print("=" * 60)

            total_start = time.time()

            # ----- Step 1: RAG retrieval -----
            print("\n  [1/6] Searching schema for relevant columns...")
            context = search_schema(user_question, limit=10)

            if not context:
                print("  [!] No schema context found. Run embed_schema.py first.")
                continue

            print("  Retrieved:")
            for table, column, desc, dist in context:
                print("    - %s.%s (distance: %.4f)" % (table, column, dist))

            # ----- Step 2: Generate SQL (with retry loop) -----
            MAX_RETRIES = 3
            sql = None
            columns = None
            rows = None
            exec_time_ms = 0
            sql_succeeded = False

            for attempt in range(1, MAX_RETRIES + 1):
                if attempt == 1:
                    print("\n  [2/6] Generating SQL with %s..." % SQL_MODEL)
                    sql_prompt = build_sql_prompt(user_question, context)
                else:
                    print("\n  [2/6] Retry %d/%d -- Sending error back to %s for correction..." % (
                        attempt, MAX_RETRIES, SQL_MODEL))
                    sql_prompt = build_correction_prompt(
                        user_question, sql, error_msg, context
                    )

                start = time.time()
                raw_sql = call_ollama(SQL_MODEL, sql_prompt)
                sql_time = time.time() - start

                if not raw_sql:
                    print("  [!] Failed to generate SQL.")
                    break

                sql = extract_sql(raw_sql)
                print("  SQL generated in %.1fs:" % sql_time)
                print("  %s" % sql)

                # ----- Step 3: Execute SQL -----
                print("\n  [3/6] Executing SQL (attempt %d/%d)..." % (attempt, MAX_RETRIES))
                start = time.time()
                columns, rows = execute_sql(sql)
                exec_time_ms = int((time.time() - start) * 1000)

                if columns is None:
                    error_msg = str(rows)
                    print("  [!] SQL execution error: %s" % error_msg)

                    # Try programmatic auto-fix first (instant, no LLM call needed)
                    current_sql = sql
                    current_error = error_msg
                    for fix_attempt in range(10):
                        auto_fixed = auto_fix_missing_join(current_sql, current_error)
                        if not auto_fixed:
                            auto_fixed = auto_fix_type_mismatch(current_sql, current_error)
                        if not auto_fixed:
                            auto_fixed = auto_fix_wrong_column_table(current_sql, current_error)
                        if not auto_fixed:
                            auto_fixed = auto_fix_bad_alias(current_sql, current_error)
                        
                        if auto_fixed:
                            print("  [AUTO-FIX] Applying programmatic fix...")
                            print("\n  [3/6] Re-executing auto-fixed SQL...")
                            start = time.time()
                            columns, rows = execute_sql(auto_fixed)
                            exec_time_ms = int((time.time() - start) * 1000)

                            if columns is not None:
                                sql = auto_fixed
                                sql_succeeded = True
                                print("  Returned %d rows, %d columns (%dms)" % (
                                    len(rows), len(columns), exec_time_ms))
                                print("  [OK] Auto-fix succeeded!")
                                break
                            else:
                                print("  [!] Auto-fix hit another error: %s" % str(rows))
                                current_sql = auto_fixed
                                current_error = str(rows)
                                error_msg = current_error # Update for LLM fallback
                        else:
                            break # No known auto-fix for this error

                    if not sql_succeeded:
                        if attempt < MAX_RETRIES:
                            print("  Sending error back to LLM for correction...")
                        else:
                            print("  [!] All %d attempts failed. Giving up." % MAX_RETRIES)
                            log_query(1, user_question, sql, False, exec_time_ms, error_msg)
                    else:
                        break # Successfully auto-fixed, exit the LLM attempt loop
                else:
                    sql_succeeded = True
                    print("  Returned %d rows, %d columns (%dms)" % (
                        len(rows), len(columns), exec_time_ms))
                    if attempt > 1:
                        print("  [OK] SQL corrected successfully on attempt %d!" % attempt)
                    break

            if not sql_succeeded:
                continue

            # ----- Step 4: Decide output type -----
            print("\n  [4/6] Classifying output type with %s..." % ANSWER_MODEL)
            output_type = decide_output_type(user_question)
            print("  Output type: %s" % output_type)

            # ----- Step 5: Synthesize answer -----
            print("\n  [5/6] Synthesizing answer with %s..." % ANSWER_MODEL)
            answer_prompt = build_answer_prompt(user_question, sql, columns, rows)

            start = time.time()
            answer = call_ollama(ANSWER_MODEL, answer_prompt, temperature=0.3)
            answer_time = time.time() - start

            # ----- Step 6: Log and display -----
            total_time = time.time() - total_start

            # Always print answer in terminal
            if answer:
                print("\n" + "=" * 60)
                print("ANSWER (%.1fs total):" % total_time)
                print("-" * 60)
                print(answer)
                print("-" * 60)
                print("Output Type: %s" % output_type.upper())
                print("=" * 60)
                log_query(1, user_question, sql, True, exec_time_ms, answer, output_type)
            else:
                print("  [!] Failed to generate answer.")
                log_query(1, user_question, sql, True, exec_time_ms,
                          "Answer generation failed", output_type)

            # Always print raw data table in terminal (max 20 rows)
            if columns and rows:
                display_rows = rows[:20]
                # Calculate column widths for clean formatting
                col_widths = []
                for i, col in enumerate(columns):
                    max_w = len(col)
                    for row in display_rows:
                        val_len = len(str(row[i])) if row[i] is not None else 4
                        if val_len > max_w:
                            max_w = val_len
                    col_widths.append(min(max_w, 30))  # Cap at 30 chars

                # Print header
                header = " | ".join(col.ljust(col_widths[i]) for i, col in enumerate(columns))
                print("\n  " + header)
                print("  " + "-" * len(header))
                # Print rows
                for row in display_rows:
                    row_str = " | ".join(
                        str(v if v is not None else "NULL")[:30].ljust(col_widths[i])
                        for i, v in enumerate(row)
                    )
                    print("  " + row_str)
                if len(rows) > 20:
                    print("  ... (%d more rows)" % (len(rows) - 20))
                print("  Total: %d rows" % len(rows))

            # Only open browser for map/bar_chart when data actually supports it
            MAX_MAP_POINTS = 2000
            MAX_MAP_CUTOFF = 150000

            if output_type == 'map' and columns and rows:
                # Check if lat/lng columns actually exist in the result
                col_lower = [c.lower() for c in columns]
                has_lat = any(c in ('latitude', 'lat', 'detected_latitude', 'initial_latitude') for c in col_lower)
                has_lng = any(c in ('longitude', 'lng', 'lon', 'detected_longitude', 'initial_longitude') for c in col_lower)
                if has_lat and has_lng:
                    if len(rows) > MAX_MAP_CUTOFF:
                        print("\n  [!] Too many points (%d rows) for map. Showing text only." % len(rows))
                    elif len(rows) > MAX_MAP_POINTS:
                        print("\n  [!] Limiting map to %d points (out of %d rows)." % (MAX_MAP_POINTS, len(rows)))
                        render_output('map', columns, rows[:MAX_MAP_POINTS], user_question, answer or "")
                    else:
                        render_output('map', columns, rows, user_question, answer or "")
                else:
                    print("\n  [!] Map requested but no lat/lng columns in result. Skipping map.")
            elif output_type == 'bar_chart' and columns and rows:
                render_output('bar_chart', columns, rows, user_question, answer or "")
            elif output_type == 'line_chart' and columns and rows:
                render_output('line_chart', columns, rows, user_question, answer or "")
            elif output_type == 'timeline' and columns and rows:
                render_output('timeline', columns, rows, user_question, answer or "")

            print("")  # Blank line before next prompt


if __name__ == "__main__":
    main()
