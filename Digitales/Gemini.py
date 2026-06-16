from google import genai

client = genai.Client()

while True:
    pregunta = str(input("Ingresa tu pregunta: "))
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=pregunta,
    )

    print(response.text)