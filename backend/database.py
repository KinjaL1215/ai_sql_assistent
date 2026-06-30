import psycopg2

try:
  connection = psycopg2.connect(
    host="localhost",
    database="ai_sql_db",
    user="postgres",
    password="Kinjal@9824" 
    )
  print("Database connection successful!")
except Exception as e:
  print("Error connecting to the database:", e)
