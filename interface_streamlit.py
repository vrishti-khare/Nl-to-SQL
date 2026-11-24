import streamlit as st
import pandas as pd
import time

# 1. MOVE THESE TWO LINES HERE
st.set_page_config(page_title="Wargame AI", layout="wide")
st.title("Wargame AI SQL Assistant")

# Import your existing backend functions
from main import (
    call_ollama, extract_sql, execute_sql, 
    decide_output_type, build_answer_prompt,
    auto_fix_missing_join, auto_fix_type_mismatch
)
from vector_search import search_schema
from generate_sql import build_sql_prompt
from config import SQL_MODEL, ANSWER_MODEL


# Initialize chat history in the browser's session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display previous chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Capture user input
user_question = st.chat_input("Ask a question about the wargame...")

if user_question:
    # Display the user's question immediately
    with st.chat_message("user"):
        st.markdown(user_question)
    
    st.session_state.messages.append({"role": "user", "content": user_question})

    # Display the AI's thought process
    with st.chat_message("assistant"):
        status_text = st.empty()
        
        status_text.text("1. Searching database schema...")
        context = search_schema(user_question, limit=15)
        
        if not context:
            st.error("No schema context found. Run embed_schema.py first.")
            st.stop()
            
        status_text.text(f"2. Classifying output type with {ANSWER_MODEL}...")
        output_type = decide_output_type(user_question)
        
        status_text.text(f"3. Generating SQL with {SQL_MODEL}...")
        sql_prompt = build_sql_prompt(user_question, context, output_type=output_type)
        raw_sql = call_ollama(SQL_MODEL, sql_prompt)
        sql = extract_sql(raw_sql)
        
        # Show the generated SQL in an expandable box
        with st.expander("View Generated SQL"):
            st.code(sql, language="sql")
            
        status_text.text("4. Executing query...")
        columns, rows = execute_sql(sql)
        
        if columns is None:
            st.error(f"SQL Execution Error: {rows}")
            st.stop()
            
        status_text.text("5. Synthesizing final answer...")
        answer_prompt = build_answer_prompt(user_question, sql, columns, rows)
        final_answer = call_ollama(ANSWER_MODEL, answer_prompt, temperature=0.3)
        
        # Clear the status text and show the final text answer
        status_text.empty()
        st.markdown(final_answer)
        
        # Render visualizations based on the AI's classification
        if output_type != 'text' and rows:
            df = pd.DataFrame(rows, columns=columns)
            
            if output_type == 'bar_chart':
                # Assumes the first column is the label and second is the value
                if len(columns) >= 2:
                    st.bar_chart(df.set_index(columns[0])[columns[1]])
            elif output_type == 'line_chart':
                if len(columns) >= 2:
                    st.line_chart(df.set_index(columns[0])[columns[1]])
            elif output_type == 'map':
                # Streamlit requires columns named exactly 'lat' and 'lon' or 'latitude' and 'longitude'
                # Proactively rename variant column names
                rename_dict = {}
                for col in df.columns:
                    col_lower = col.lower()
                    if col_lower in ('latitude', 'lat', 'detected_latitude', 'initial_latitude'):
                        rename_dict[col] = 'latitude'
                    elif col_lower in ('longitude', 'lng', 'lon', 'detected_longitude', 'initial_longitude'):
                        rename_dict[col] = 'longitude'
                
                if rename_dict:
                    df = df.rename(columns=rename_dict)
                
                if 'latitude' in df.columns and 'longitude' in df.columns:
                    try:
                        st.map(df)
                    except Exception as e:
                        st.warning(f"Map rendering failed: {e}. Ensure your SQL returns 'latitude' and 'longitude' columns.")
                else:
                    st.warning("Map requested, but result does not contain latitude/longitude coordinate columns. Defaulting to data table.")
                    st.dataframe(df)
            else:
                st.dataframe(df) # Fallback to a data table
                
        # Save the AI's response to the chat history
        st.session_state.messages.append({"role": "assistant", "content": final_answer})

