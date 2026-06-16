# CrmConformidad/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ExpedienteConformidad
from notificaciones.services import enviar_notificacion_push

@receiver(post_save, sender=ExpedienteConformidad)
def alertar_nuevo_expediente(sender, instance, created, **kwargs):
    """
    Se ejecuta de forma automatica e inmediata en cuanto un expediente 
    se guarda de manera exitosa en la base de datos.
    """
    if created:  
       
        nombre_cliente = f"{instance.cliente.nombre} {instance.cliente.apellidos}".strip()
        titulo_push = "📋 Nuevo Expediente Asignado"
        mensaje_push = f"Se ha generado el expediente #{instance.id_exp} para el cliente: {nombre_cliente}."
        

        payload_data = {
            "id_expediente": instance.id_exp,
            "pantalla": "DetalleExpediente"
        }
        
        
        
      
        from .models import Usuario
        primer_usuario = Usuario.objects.first()
        
        if primer_usuario:
            enviar_notificacion_push(
                usuario=primer_usuario,
                titulo=titulo_push,
                mensaje=mensaje_push,
                data_extra=payload_data
            )