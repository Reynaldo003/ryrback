#Digitales/views.py
import json
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views import View
from .sett import token
from .contacto import obtener_Mensaje_whatsapp, replace_start, administrar_chatbot
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from .contacto import enviar_template

@api_view(["POST"])
@permission_classes([AllowAny])
def enviar_template_view(request):
    # opcional: permitir que el front mande un número
    to = request.data.get("to")  # puede venir vacío; usará el default
    try:
        data = enviar_template(to=to)
        return Response({"ok": True, "data": data}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"ok": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


def bienvenido(request):
    return HttpResponse("Funcionando envio de whats R&R, desde Django")

@csrf_exempt
def webhook(request):
    if request.method == "GET":
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        if token == token and challenge:
            return HttpResponse(challenge)
        return HttpResponse("token incorrecto", status=403)

    if request.method == "POST":
        try:
            body = json.loads(request.body.decode("utf-8"))
            entry = body["entry"][0]
            changes = entry["changes"][0]
            value = changes["value"]
            message = value["messages"][0]
            number = replace_start(message["from"])
            message_id = message["id"]
            name = value["contacts"][0]["profile"]["name"]
            text = obtener_Mensaje_whatsapp(message)

            administrar_chatbot(text, number, message_id, name)
            return HttpResponse("enviado")
        except Exception as e:
            return HttpResponse(f"no enviado {e}", status=400)
