import ollama

response = ollama.chat(
    model="llama3",
    messages=[
        {
            "role": "user",
            "content": "What is SQL?"
        }
    ]
)

print(response["message"]["content"])