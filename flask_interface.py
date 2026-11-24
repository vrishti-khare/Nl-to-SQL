from flask import Flask, render_template, request
from main import (
    call_ollama, extract_sql, execute_sql, 
    build_answer_prompt
)
from vector_search import search_schema
from generate_sql import build_sql_prompt
from config import SQL_MODEL, ANSWER_MODEL

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def home():
    answer_text = None
    sql_query = None
    user_q = None

    if request.method == "POST":
        user_q = request.form.get("user_question")
        
        # 1. Retrieve Schema
        context = search_schema(user_q, limit=15)
        
        if context:
            # 2. Generate SQL
            sql_prompt = build_sql_prompt(user_q, context)
            raw_sql = call_ollama(SQL_MODEL, sql_prompt)
            sql_query = extract_sql(raw_sql)
            
            # 3. Execute SQL
            columns, rows = execute_sql(sql_query)
            
            # 4. Generate Answer
            if columns is not None:
                answer_prompt = build_answer_prompt(user_q, sql_query, columns, rows)
                answer_text = call_ollama(ANSWER_MODEL, answer_prompt, temperature=0.3)
            else:
                answer_text = "Database error: " + str(rows)
        else:
            answer_text = "Error: Please run embed_schema.py first."

    return render_template("index.html", answer=answer_text, sql=sql_query, question=user_q)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)