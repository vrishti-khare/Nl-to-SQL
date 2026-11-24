"""
=============================================================
Wargame SQL Generator Prompt Builder
=============================================================
Provides the central Database Schema DDL and prompt builder for
translating natural language questions into SQL.
=============================================================
"""

# Centralized DDL representing all 11 tables in the database schema.
# Used by the LLM to understand columns, types, and joins.
SCHEMA_DDL = """
-- Table 1: game
CREATE TABLE game (
    game_id              SERIAL PRIMARY KEY,
    scenario_name        VARCHAR(255) NOT NULL,
    scenario_objective   TEXT,
    game_outcome         VARCHAR(50),
    weather_condition    VARCHAR(50) DEFAULT 'Clear',
    start_clock          INTEGER NOT NULL DEFAULT 0,
    end_clock            INTEGER NOT NULL,
    clock_interval       INTEGER NOT NULL DEFAULT 1,
    game_start_real_time TIMESTAMP NOT NULL,
    date_played          DATE NOT NULL DEFAULT CURRENT_DATE,
    total_forces         INTEGER NOT NULL DEFAULT 4
);

-- Table 2: force
CREATE TABLE force (
    force_id         SERIAL PRIMARY KEY,
    game_id          INTEGER NOT NULL REFERENCES game(game_id) ON DELETE CASCADE,
    force_name       VARCHAR(50) NOT NULL,   -- e.g., 'Blue', 'Red', 'Green', 'Yellow'
    commander_name   VARCHAR(255),
    total_platforms  INTEGER NOT NULL DEFAULT 0
);

-- Table 3: platform_profile
CREATE TABLE platform_profile (
    platform_id        SERIAL PRIMARY KEY,
    force_id           INTEGER NOT NULL REFERENCES force(force_id) ON DELETE CASCADE,
    game_id            INTEGER NOT NULL REFERENCES game(game_id) ON DELETE CASCADE,
    platform_name      VARCHAR(255) NOT NULL,
    platform_type      VARCHAR(50) NOT NULL,   -- 'ship', 'aircraft', 'submarine'
    max_fuel_capacity  REAL NOT NULL,
    fuel_type          VARCHAR(50) DEFAULT 'Diesel',
    max_speed_knots    REAL NOT NULL,
    max_crew           INTEGER NOT NULL,
    radar_range_km     REAL DEFAULT 0.0,
    sonar_range_km     REAL DEFAULT 0.0,
    weapon_load        VARCHAR(255),
    initial_latitude   REAL NOT NULL,
    initial_longitude  REAL NOT NULL
);

-- Table 4: zone_boundaries
CREATE TABLE zone_boundaries (
    zone_id               SERIAL PRIMARY KEY,
    game_id               INTEGER NOT NULL REFERENCES game(game_id) ON DELETE CASCADE,
    zone_name             VARCHAR(100) NOT NULL,  -- e.g. 'Zone Alpha'
    boundary_coordinates  TEXT NOT NULL,          -- JSON array of lat/lng points
    zone_type             VARCHAR(50) NOT NULL,    -- 'patrol', 'exclusion', 'objective', 'neutral'
    description           TEXT
);

-- Table 5: platform_telemetry_log
CREATE TABLE platform_telemetry_log (
    log_id                  SERIAL PRIMARY KEY,
    game_id                 INTEGER NOT NULL REFERENCES game(game_id) ON DELETE CASCADE,
    platform_id             INTEGER NOT NULL REFERENCES platform_profile(platform_id) ON DELETE CASCADE,
    force_id                INTEGER NOT NULL REFERENCES force(force_id) ON DELETE CASCADE,
    clock_tick              INTEGER NOT NULL,
    real_timestamp          TIMESTAMP NOT NULL,
    latitude                REAL NOT NULL,
    longitude               REAL NOT NULL,
    speed_knots             REAL NOT NULL DEFAULT 0.0,
    course_deg              REAL DEFAULT 0.0,
    heading_deg             REAL DEFAULT 0.0,
    altitude_meters         REAL DEFAULT 0.0,
    depth_meters            REAL DEFAULT 0.0,
    fuel_level              REAL NOT NULL,
    fuel_consumed_interval  REAL DEFAULT 0.0,
    crew_count              INTEGER NOT NULL,
    radar_status            VARCHAR(20) DEFAULT 'Off',  -- 'On', 'Off'
    radar_range_active_km   REAL DEFAULT 0.0,
    sonar_status            VARCHAR(20) DEFAULT 'Off',  -- 'On', 'Off'
    weapon_status           VARCHAR(20) DEFAULT 'Safe',
    engine_status           VARCHAR(20) DEFAULT 'Normal',
    hull_integrity_pct      REAL DEFAULT 100.0,
    communication_status    VARCHAR(20) DEFAULT 'Online',
    operational_status      VARCHAR(20) DEFAULT 'Active', -- 'Active', 'Destroyed', 'Damaged'
    current_zone            VARCHAR(100),
    visibility_km           REAL DEFAULT 20.0,
    sea_state               INTEGER DEFAULT 3,
    alert_flag              BOOLEAN DEFAULT FALSE,
    alert_description       VARCHAR(255)
);

-- Table 6: tactical_actions
CREATE TABLE tactical_actions (
    action_id            SERIAL PRIMARY KEY,
    game_id              INTEGER NOT NULL REFERENCES game(game_id) ON DELETE CASCADE,
    platform_id          INTEGER NOT NULL REFERENCES platform_profile(platform_id) ON DELETE CASCADE,
    force_id             INTEGER NOT NULL REFERENCES force(force_id) ON DELETE CASCADE,
    clock_tick           INTEGER NOT NULL,
    real_timestamp       TIMESTAMP NOT NULL,
    action_type          VARCHAR(50) NOT NULL, -- e.g. 'Radar Detection', 'Launch Missile', 'Sonar Ping'
    target_platform_id   INTEGER REFERENCES platform_profile(platform_id) ON DELETE SET NULL,
    outcome              VARCHAR(20),          -- 'success', 'failed', 'partial'
    zone_id              INTEGER REFERENCES zone_boundaries(zone_id) ON DELETE SET NULL,
    notes                TEXT
);

-- Table 7: messages
CREATE TABLE messages (
    message_id           SERIAL PRIMARY KEY,
    game_id              INTEGER NOT NULL REFERENCES game(game_id) ON DELETE CASCADE,
    sender_platform_id   INTEGER NOT NULL REFERENCES platform_profile(platform_id) ON DELETE CASCADE,
    receiver_platform_id INTEGER REFERENCES platform_profile(platform_id) ON DELETE SET NULL,
    clock_tick           INTEGER NOT NULL,
    real_timestamp       TIMESTAMP NOT NULL,
    message_content      TEXT NOT NULL,
    message_type         VARCHAR(50) NOT NULL,  -- 'tactical', 'informational', 'distress', 'command'
    is_broadcast         BOOLEAN DEFAULT FALSE,
    broadcast_scope      VARCHAR(50)            -- 'ALL_FORCES', 'OWN_FORCE', NULL if direct
);

-- Table 8: detection_log
CREATE TABLE detection_log (
    detection_id             SERIAL PRIMARY KEY,
    game_id                  INTEGER NOT NULL REFERENCES game(game_id) ON DELETE CASCADE,
    clock_tick               INTEGER NOT NULL,
    real_timestamp           TIMESTAMP NOT NULL,
    detecting_platform_id    INTEGER NOT NULL REFERENCES platform_profile(platform_id) ON DELETE CASCADE,
    detecting_force_id       INTEGER NOT NULL REFERENCES force(force_id) ON DELETE CASCADE,
    detected_platform_id     INTEGER NOT NULL REFERENCES platform_profile(platform_id) ON DELETE CASCADE,
    detected_force_id        INTEGER NOT NULL REFERENCES force(force_id) ON DELETE CASCADE,
    detection_range_km       REAL NOT NULL,
    detected_latitude        REAL,
    detected_longitude       REAL,
    detection_confidence     VARCHAR(50) DEFAULT 'Probable',
    detection_method         VARCHAR(50) DEFAULT 'Radar', -- 'Radar', 'Sonar', 'Visual'
    detection_lost_tick      INTEGER,
    detection_lost_timestamp TIMESTAMP,
    detection_duration_ticks INTEGER
);

-- Table 9: main_consolidated_log (Flattened unified view of telemetry & messages)
CREATE TABLE main_consolidated_log (
    consolidated_id        SERIAL PRIMARY KEY,
    game_id                INTEGER NOT NULL REFERENCES game(game_id) ON DELETE CASCADE,
    clock_tick             INTEGER NOT NULL,
    real_timestamp         TIMESTAMP NOT NULL,
    force_id               INTEGER NOT NULL REFERENCES force(force_id) ON DELETE CASCADE,
    force_name             VARCHAR(50),
    platform_id            INTEGER NOT NULL REFERENCES platform_profile(platform_id) ON DELETE CASCADE,
    platform_name          VARCHAR(255),
    platform_type          VARCHAR(50),
    latitude               REAL,
    longitude              REAL,
    speed_knots            REAL,
    course_deg             REAL,
    altitude_meters        REAL DEFAULT 0.0,
    depth_meters           REAL DEFAULT 0.0,
    fuel_level             REAL,
    fuel_consumed_interval REAL,
    radar_status           VARCHAR(20),
    sonar_status           VARCHAR(20),
    hull_integrity_pct     REAL,
    current_zone           VARCHAR(100),
    visibility_km          REAL,
    sea_state              INTEGER,
    operational_status     VARCHAR(20),
    message_sent           BOOLEAN DEFAULT FALSE,
    message_type           VARCHAR(50),
    message_id             INTEGER REFERENCES messages(message_id) ON DELETE SET NULL
);
"""


def build_sql_prompt(user_question, context, output_type=None):
    """
    Constructs the prompt for the SQLCoder / Qwen-Coder model.
    
    Args:
        user_question (str): The natural language query.
        context (list): Retrieved list of tuples (table_name, column_name, description, distance)
        output_type (str, optional): The expected output format ('map', 'line_chart', etc.)
        
    Returns:
        str: Prompt formatted for code generation.
    """
    # Format retrieved columns context for the LLM
    context_str = ""
    for row in context:
        table, col, desc = row[0], row[1], row[2]
        context_str += f"- {table}.{col}: {desc}\n"

    prompt = "### Task\n"
    prompt += "Generate a PostgreSQL query to answer the user question. Follow these instructions precisely:\n"
    prompt += "1. Use ONLY PostgreSQL 17 compatible syntax.\n"
    prompt += "2. Return ONLY the executable SQL query, wrapped inside a markdown code block (```sql ... ```). Do not include any description or explanation.\n"
    prompt += "3. Use ONLY the tables and columns present in the schema DDL below. Do NOT reference or join tables/columns not defined in the DDL.\n"
    prompt += "4. If joining tables, always qualify column names with their table name to avoid ambiguity.\n"
    prompt += "5. Pay close attention to the list of Relevant Columns retrieved from the database structure.\n"
    prompt += "6. CRITICAL: When the question refers to 'the start of the game' or 'initial positions', filter by `clock_tick = 0` or query `initial_latitude` and `initial_longitude` from `platform_profile`.\n"
    prompt += "7. CRITICAL: When referencing a specific game like 'game 1', filter by `game_id = 1` in the WHERE clause.\n"
    prompt += "8. CRITICAL: When referencing a force name (e.g. 'Force Red', 'Blue force'), join the `force` table and match on `force.force_name = 'Red'` or `force.force_name = 'Blue'`. DO NOT match against `commander_name` unless commander is explicitly mentioned.\n"
    prompt += "9. CRITICAL: For questions about missiles fired or launched, query `tactical_actions` and filter by `action_type = 'MISSILE_FIRED'`. Use COUNT(*) or COUNT(action_id) to count the number of missiles.\n"
    prompt += "10. CRITICAL: Never reference non-existent tables such as `tactical_platforms` or `platform_telemetry`. Use only the tables defined in the schema DDL.\n"
    
    # Inject visualization constraints if output_type is specified
    if output_type == 'map':
        prompt += "11. CRITICAL: The user wants to see a map visualization. You MUST select latitude and longitude columns (e.g. `latitude` and `longitude` from telemetry/consolidated logs, `detected_latitude` and `detected_longitude` from detection logs, or `initial_latitude` and `initial_longitude` from platform profiles) from the appropriate tables so they can be plotted on the map.\n\n"
    elif output_type == 'line_chart':
        prompt += "11. CRITICAL: The user wants to see a line chart. You MUST select a time/tick column (like `clock_tick` or `real_timestamp`) and at least one numeric column to plot over time.\n\n"
    elif output_type == 'bar_chart':
        prompt += "11. CRITICAL: The user wants to see a bar chart. You MUST select a categorical column (like `platform_name` or `force_name`) and a numeric column to compare/rank values.\n\n"
    elif output_type == 'timeline':
        prompt += "11. CRITICAL: The user wants to see a timeline. You MUST select a time/tick column (like `clock_tick` or `real_timestamp`) and a descriptive/action column (like `action_type` or `notes` or `message_content`).\n\n"
    else:
        prompt += "\n"
    
    # Add few-shot examples
    prompt += "### Example Queries and Correct SQL\n"
    prompt += "Question: `How many missiles did Force Red fire in game 1?`\n"
    prompt += "SQL:\n"
    prompt += "```sql\n"
    prompt += "SELECT COUNT(*) AS missiles_fired FROM tactical_actions ta JOIN force f ON ta.force_id = f.force_id WHERE f.force_name = 'Red' AND ta.action_type = 'MISSILE_FIRED' AND ta.game_id = 1;\n"
    prompt += "```\n\n"
    
    prompt += "Question: `What is the hull damage on Red force ships in game 1?`\n"
    prompt += "SQL:\n"
    prompt += "```sql\n"
    prompt += "SELECT DISTINCT platform_name, hull_integrity_pct FROM main_consolidated_log WHERE force_name = 'Red' AND platform_type = 'ship' AND game_id = 1;\n"
    prompt += "```\n\n"
    
    prompt += "### Database Schema DDL\n"
    prompt += SCHEMA_DDL + "\n\n"
    
    prompt += "### Relevant Columns (RAG retrieved)\n"
    prompt += context_str + "\n"
    
    prompt += "### Question\n"
    prompt += f"`{user_question}`\n\n"
    
    prompt += "### SQL Query\n"
    
    return prompt
