#Digitales/sett.py
token = 'CBAR&RVOLKS'
whatsapp_token = 'EAAS1RWxgIcIBP8LS2l1ZAmUz4BjZCufH0VUVQCS4KQhAbAPFQtHtsbgZAVZBF8W1HjFbwur6qtN3KokHoZBY2qpZA24MafOc2bnc1SuXVK2EWT2qsGVnE4oltrQyFOYPN9rEwXFd1ZAHYvPktu7HlsoYThbThNHRwHR6PdkN8TfgZBJWEAMb1VnJsdSYSXRKegZDZD'
whatsapp_token_tuxtepec = 'EAAVlkKROgagBRdZAyzfeyZAQL0ZBwGZBSOunNx57FoXkLzTdDeA54vOBMOZCge18ttvMvprzSybCySol3ZBzCiAkfJLJzbN6bX0ISHlRl4JoTmYc1p09A4HM3MT7ZAiVFLTAXfKxFll9HNuDTVkZAHluYqYZB5sdZBlkuMBQsJd9GD4ZBmymlFwM60kBEF0VhMAjgZDZD'
whatsapp_token_tuxpan = 'EAATUD4lFmroBRjhEo3n9bvR0PZA0sC68SnabSaRJq7ZCgL2CRufeST4zxF4RWxpOrKKFNQW6voMx4YCoDDANlHtVaPUZCaNimJCy5wb5pqrnNMvAZC9aNPZBx721Ek5HotcKjaqinWhe6QZAROZCYlk74v3nBdOTt0NHree5FY09pizUkvwW0KI9Lf1qWUTYnILRAZDZD'

META_ADS_CORDOBA = {
    "app_id": "3593225937645317",
    "app_secret": "7c7a556808e02f3f4928689ee2d742fe",
    "access_token": "EAAzEBRucbwUBRoV0ufLGYyEXbpXt3VRVz1Ca7cXjyzwUA8BNNCVj07UJip0bJYSS2w0G6jZAulzgwI0fmq4IaOxuATS7RZCEZAwTqnQqIAAIT9eWiUuszZCJXf0ZBFLyXZCiyhXPYXnPDuoJZC4ym307GfXK2I6PyV5qVAj4Oo4IkANNrSRwZBm0NFXmsCZBJ3tUi6ZCn68nO2pywMtMZAdPZACI",
    "ad_account_id": "act_1073055867404337",
}

META_ADS_ORIZABA = {
    "app_id": "3593225937645317",
    "app_secret": "7c7a556808e02f3f4928689ee2d742fe",
    "access_token": "EAAzEBRucbwUBRoV0ufLGYyEXbpXt3VRVz1Ca7cXjyzwUA8BNNCVj07UJip0bJYSS2w0G6jZAulzgwI0fmq4IaOxuATS7RZCEZAwTqnQqIAAIT9eWiUuszZCJXf0ZBFLyXZCiyhXPYXnPDuoJZC4ym307GfXK2I6PyV5qVAj4Oo4IkANNrSRwZBm0NFXmsCZBJ3tUi6ZCn68nO2pywMtMZAdPZACI",
    "ad_account_id": "act_732515889137747",
}

META_ADS_TUXPAN_POZA_RICA = {
    "app_id": "1553066005988692",
    "app_secret": "7dc6f4fc1ec280fbd90b76d47f205af8",
    "access_token": "EAAWEgVuZAhVQBRh2cbyFZBIvjePfHHZC1jZCUzrKmpAZCgZAPKFfZCYP3P3DDr72Ym9G757eYGokvXKZBF1v2sIFmOyZBOSljZBjVDZCuuq3XBsbOaguoEV3forMS0AFsevEYAotm2QxDOyeeEbptNChJMPmW7Xo3f3FPgnaK5Is1j2SlMdPZBuIauhjREgE7JhLfgTZCX99fdNbUj2kez0ijO5Ot",
    "ad_account_id": "act_296954953129651",
}

META_ADS_TUXTEPEC = {
    "app_id": "1613901002943549",
    "app_secret": "338b9fee518e9d0463c88d4b191f3c8a",
    "access_token": "EAAW71ZAv7rD0BRie6g9zjoZCIdxNb4E37EV7zTTXktyFdSDUgZBSIAKr54ZBgNnNaZASEkxPjNrjVnx5zsJIUwYwiLZAZC9cz6NG7etmIwtcxoTjZCnoBHf8esSZAhqd70t3WrmeawRJulXBluRe6NdRfinmn21aNZC9y2JupIDeplzlZAnyPcryaJNWQaIejWGSuuAanP74s35AxBQk18EvbEL",
    "ad_account_id": "act_643975770287544",
}


def meta_ads_linea(cfg: dict) -> dict:
    return {
        "meta_ads_app_id": cfg["app_id"],
        "meta_ads_app_secret": cfg["app_secret"],
        "meta_ads_access_token": cfg["access_token"],
        "meta_ads_ad_account_id": cfg["ad_account_id"],
        "meta_ads_ad_account_ids": [cfg["ad_account_id"]],
    }


META_ADS_ACCESS_TOKEN = ""

GRAPH_VERSION = "v22.0"
WHATSAPP_WABA_ID_DEFAULT = "TU_WHATSAPP_BUSINESS_ACCOUNT_ID"

whatsapp_url = 'https://graph.facebook.com/v22.0/836147029587691/messages'
whatsapp_url_liz = 'https://graph.facebook.com/v22.0/1002516582953413/messages'
whatsapp_url_eren = 'https://graph.facebook.com/v22.0/970758852797236/messages'
whatsapp_url_bianca = 'https://graph.facebook.com/v22.0/1118159131375259/messages'
whatsapp_url_denisse = 'https://graph.facebook.com/v22.0/1134322799754327/messages'
whatsapp_url_marelly = 'https://graph.facebook.com/v22.0/1113085168553604/messages'
whatsapp_url_edgar = 'https://graph.facebook.com/v22.0/1208561865665780/messages'

whatsapp_numero_default = "522712638803"
whatsapp_numero_liz = "522721111244"
whatsapp_numero_eren = "522713133332"
whatsapp_numero_bianca = "522712837999"
whatsapp_numero_denisse = "522721986539"
whatsapp_numero_marelly = "522871232641"
whatsapp_numero_edgar = "527831263814"

WHATSAPP_LINES = {
    whatsapp_numero_default: {
        "key": "default",
        "phone_number_id": "836147029587691",
        "waba_id": "1487171602543671",
        "access_token": whatsapp_token,
        "asesor_digital": "IA Vagen",
        "messages_url": whatsapp_url,
        "agencia": "VW Cordoba",
        "business": "Comerciales",
        "responder_ia": True,
        "template_names": ["saludo_seguimiento", "informacion_seguimiento"],
        **meta_ads_linea(META_ADS_CORDOBA),
    },

    whatsapp_numero_liz: {
        "key": "liz",
        "phone_number_id": "1002516582953413",
        "waba_id": "1448342956973453",
        "access_token": whatsapp_token,
        "asesor_digital": "Lizbeth Cano Clara",
        "messages_url": whatsapp_url_liz,
        "agencia": "VW Orizaba",
        "business": "Nuevos",
        "responder_ia": False,
        "template_names": ["saludo_seguimiento", "confirmacion_cita", "informacion_seguimiento", "seguimiento_sin_respuesta", "primer_contacto_nuevos", "primer_contacto_nuevo_dos", "confirmacion_visita", "seguimiento_pendiente_visita", "reagenda_cita", "address_update"],
        **meta_ads_linea(META_ADS_ORIZABA),
    },

    whatsapp_numero_eren: {
        "key": "eren",
        "phone_number_id": "970758852797236",
        "waba_id": "2822606908081116",
        "access_token": whatsapp_token,
        "asesor_digital": "Erendira Santos Coyotzi",
        "messages_url": whatsapp_url_eren,
        "agencia": "VW Cordoba",
        "business": "Nuevos",
        "responder_ia": False,
        "template_names": ["saludo_seguimiento", "informacion_seguimiento", "confirmar_cita", "seguimiento_dos", "recontacto", "requisitos_vw", "presentacion", "seguimiento_salesforce", "ultimo_seguimiento_force"],
        **meta_ads_linea(META_ADS_CORDOBA),
    },
    whatsapp_numero_bianca: {
        "key": "bianca",
        "phone_number_id": "1118159131375259",
        "waba_id": "1674154250377394",
        "access_token": whatsapp_token,
        "asesor_digital": "Bianca Chavez Alarcon",
        "messages_url": whatsapp_url_bianca,
        "agencia": "VW Cordoba Usados",
        "business": "Usados",
        "responder_ia": False,
        "template_names": ["saludo_seguimiento", "informacion_seguimiento"],
        **meta_ads_linea(META_ADS_CORDOBA),
    },

    whatsapp_numero_denisse: {
        "key": "denisse",
        "phone_number_id": "1134322799754327",
        "waba_id": "1512733033596137",
        "access_token": whatsapp_token,
        "asesor_digital": "Candy Denisse Marquez",
        "messages_url": whatsapp_url_denisse,
        "agencia": "VW Orizaba Usados",
        "business": "Usados",
        "responder_ia": False,
        "template_names": ["saludo_seguimiento", "informacion_seguimiento"],
        **meta_ads_linea(META_ADS_ORIZABA),
    },

    whatsapp_numero_marelly: {
        "key": "marelly",
        "phone_number_id": "1113085168553604",
        "waba_id": "1447380546688132",
        "access_token": whatsapp_token_tuxtepec,
        "asesor_digital": "Marelly Tenorio Salinas",
        "messages_url": whatsapp_url_marelly,
        "agencia": "VW Tuxtepec",
        "business": "Nuevos",
        "responder_ia": False,
        "template_names": ["saludo_seguimiento", "informacion_seguimiento"],
        **meta_ads_linea(META_ADS_TUXTEPEC),
    },
    whatsapp_numero_edgar: {
        "key": "edgar",
        "phone_number_id": "1208561865665780",
        "waba_id": "1271948571437191",
        "access_token": whatsapp_token_tuxpan,
        "asesor_digital": "Edgar Omar Nogera Solis",
        "messages_url": whatsapp_url_edgar,
        "agencia": "VW Tuxpan",
        "business": "Nuevos",
        "responder_ia": False,
        "template_names": ["cita_confirmacion", "seguimiento_saludo"],
        **meta_ads_linea(META_ADS_TUXPAN_POZA_RICA),
    },
}

WHATSAPP_PHONE_ID_TO_NUMBER = {
    str(cfg["phone_number_id"]): numero
    for numero, cfg in WHATSAPP_LINES.items()
}

WHATSAPP_TEMPLATE_UI = {
    "saludo_seguimiento": {
        "title": "Saludo de seguimiento",
        "help": "",
        "labels": {
            "body_1": "Nombre del prospecto",
            "body_2": "Interés del prospecto",
            "body_3": "Acción de seguimiento",
        },
    },
    "informacion_seguimiento": {
        "title": "Seguimiento",
        "help": "",
        "labels": {
            "body_1": "usuario",
            "body_2": "instalaciones",
            "body_3": "experiencia",
            "body_4": "de",
        },
    },
    "confirmar_cita": {
        "title": "Seguimiento",
        "help": "",
        "labels": {
            "body_1": "dia",
            "body_2": "hora",
        },
    },
    "seguimiento_sin_respuesta": {
        "title": "Seguimiento Interés",
        "help": "",
        "labels": {
            "body_1": "Cliente",
        },
    },
    "primer_contacto_nuevo_dos": {
        "title": "Primer Contacto",
        "help": "",
        "labels": {
            "body_1": "amigo",
        },
    },
    "recontacto": {
        "title": "Recontacto",
        "help": "",
        "labels": {
            "body_1": "la hora",
        },
    },
    "confirmacion_visita": {
        "title": "Confirmacion Visita",
        "help": "",
        "labels": {
            "body_1": "dia",
            "body_2": "hora",
        },
    },
    "cita_confirmacion": {
        "title": "",
        "help": "",
        "labels": {
            "body_1": "hora",
            "body_2": "fecha",
        },
    },
    "ultimo_seguimiento_force": {
        "title": "",
        "help": "",
        "labels": {
            "body_1": "John",
        },
    },
    "address_update": {
        "title": "",
        "help": "",
        "labels": {
            "body_1": "ayuda",
        },
    },
    "reagenda_cita": {
        "title": "",
        "help": "",
        "labels": {
            "body_1": "ayer",
        },
    },
}