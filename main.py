from twilio.rest import Client
from flask import Flask, Response, jsonify, request
import psycopg2
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
import os
import logging
from openai import OpenAI


load_dotenv()

client_opneai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,  
    format='%(asctime)s [%(levelname)s] %(message)s',  
    handlers=[
        logging.FileHandler("app.log"),   
        logging.StreamHandler()          
    ]
)

logger = logging.getLogger(__name__)

client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))

def get_db_connection():
    try:
        conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
        )
        return conn
    except Exception as e:
        logger.error(f"Coneccion fallida Postgres: {e}")
        raise

def get_or_create_cliente_id(numero, nombre="desconocido"):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # buscl al cliente por numero de telefono
        cursor.execute("SELECT id FROM cliente WHERE telefono = %s", (numero,))
        result = cursor.fetchone()

        if result:
            return result[0]
        else:
            # Crear cliente nuevo si no existe
            cursor.execute(
                "INSERT INTO cliente (telefono, nombre) VALUES (%s, %s) RETURNING id",
                (numero, nombre)
            )
            cliente_id = cursor.fetchone()[0]
            conn.commit()
            logger.info(f"Cliente creado con ID: {cliente_id}")
            return cliente_id

    except Exception as e:
        logger.error(f"Error en get_or_create_cliente_id: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()




from datetime import date

def get_conversacion_id(cliente_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Intentar recuperar una conversación existente para hoy
        cursor.execute(
            """
            SELECT id FROM conversacion
            WHERE cliente_id = %s AND fecha = %s
            ORDER BY id DESC LIMIT 1
            """,
            (cliente_id, date.today())
        )
        result = cursor.fetchone()

        if result:
            return result[0]
        else:
            # Crear una nueva conversación
            descripcion = f"Conversación iniciada el {date.today()}"
            cursor.execute(
                """
                INSERT INTO conversacion (fecha, descripcion, cliente_id)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (date.today(), descripcion, cliente_id)
            )
            conversacion_id = cursor.fetchone()[0]
            conn.commit()
            logger.info(f"Conversación creada con ID: {conversacion_id}")
            return conversacion_id

    except Exception as e:
        logger.error(f"Error al obtener o crear conversación: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()

def store_message_twilio(conversation_id, response_ia):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO mensaje (
                tipo,
                contenido_texto,
                media_url,
                media_mimetype,
                media_filename,
                conversacion_id
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                "ia",                 # tipo del mensaje
                response_ia,          # contenido generado por IA
                None,                 # media_url
                None,                 # media_mimetype
                None,                 # media_filename
                conversation_id       # ID de la conversación
            )
        )
        conn.commit()
        logger.info("Respuesta de IA guardada en la base de datos")

    except Exception as e:
        logger.error(f"Error guardando respuesta IA: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()



def store_message(conversation_id, requestfull):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        num_media = int(requestfull.get("NumMedia", 0))
        message_type = requestfull.get("MessageType", "text")
        body = requestfull.get("Body", "")
        media_url = None
        media_mimetype = None
        media_filename = None  

        if num_media > 0:
            media_url = requestfull.get("MediaUrl0")
            media_mimetype = requestfull.get("MediaContentType0")
            # intentar deducir un nombre por extensión
            ext = media_mimetype.split("/")[-1] if media_mimetype else "bin"
            media_filename = f"media.{ext}"
        
        cursor.execute(
            """
            INSERT INTO mensaje (
                tipo,
                contenido_texto,
                media_url,
                media_mimetype,
                media_filename,
                conversacion_id
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                message_type,
                body if body else None,
                media_url,
                media_mimetype,
                media_filename,
                conversation_id
            )
        )

        conn.commit()
        logger.info("Mensaje guardado en la base de datos")

    except Exception as e:
        logger.error(f"Error guardando mensaje: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
def generate_response_ia(question, conversacion_id):
    
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Obtener historial de conversación
        cursor.execute("""
            SELECT contenido_texto
            FROM mensaje
            WHERE conversacion_id = %s
            AND contenido_texto IS NOT NULL
            ORDER BY id ASC
        """, (conversacion_id,))
        historial = cursor.fetchall()
        historial_texto = "\n".join([fila[0] for fila in historial if fila[0]])

        # Obtener lista de productos
        cursor.execute("""
            SELECT nombre, descripcion
            FROM producto
        """)
        productos = cursor.fetchall()
        productos_texto = "\n".join([f"{nombre}: {descripcion}" for nombre, descripcion in productos])

        # Construir prompt
        prompt = f"""Contexto del cliente:
        {historial_texto}

        Catálogo de productos que tenemos:
        {productos_texto}

        Mensaje nuevo del cliente o pregunta:
        {question}

        Responde de manera útil, clara y separa tus ideas con saltos de línea. Si mencionas varios productos, usa una lista con guiones. Evita respuestas en una sola línea, separa los párrafos para mejorar la legibilidad.
        
        si el mensaje es solo saludo o preguntas no mensiones los productos, solo si la pregunta esta realcionada o sugiere los productos que tenemos tambien te pase el contexto del cliente 
        
        tambien te pase el historial de convezacion, porsi las preguntas estan relacionadas hacia la conversacion o recordar la charla
        """

        # Llamada a OpenAI
        response = client_opneai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente de ventas amigable."},
                {"role": "user", "content": prompt}
            ]
        )


        respuesta_texto = response.choices[0].message.content
        print("Respuesta IA:", respuesta_texto)
        logger.info(f"Respuesta IA generada: {respuesta_texto}")
        return respuesta_texto

    except Exception as e:
        logger.error(f"Error en generate_response_ia: {e}")
        return "Lo siento, ocurrió un error al generar la respuesta."
    finally:
        cursor.close()
        conn.close()
 

@app.route('/webhook', methods=['POST'])
def webhook():
    # Obtener datos del mensaje
    from_number = request.form.get('From')
    body = request.form.get('Body')

    print(f'Mensaje recibido de {from_number}: {body}')
    
    requestt = request.form


    try:
        logger.warning(f"Datos completos recibidos: {request.form}")
        # Obtener datos del mensaje
        body = request.form.get('Body', '')
        from_number = request.form.get('From')
        
        numero = from_number.replace('whatsapp:', '')  # numero sin el texto  "whatsapp:"
        logger.warning(f"Mensaje entrante {from_number}: msg: {body}")
        
        cliente_id = get_or_create_cliente_id(numero)
        get_converzacion_id = get_conversacion_id(cliente_id)
        
        store_message(
            conversation_id=get_converzacion_id,
            requestfull= requestt
            )
        
         
        respuesta_ia =generate_response_ia(
            question=body ,
            conversacion_id= get_converzacion_id
            )
        if respuesta_ia:
            store_message_twilio(
                conversation_id=get_converzacion_id,
                response_ia=respuesta_ia
            )
        
        #response = MessagingResponse()
        #response.message(f"Hola, recibimos tu mensaje: {respuesta_ia} , Conversacion id: {get_converzacion_id}")
        response_text = (
                            f"Hola\n\n"
                            f"Recibimos tu mensaje :\n\n"
                            f"{respuesta_ia}\n\n"
                            f"🆔 Conversación ID: {get_converzacion_id}"
                        )
        response = MessagingResponse()
        response.message(response_text)
        return str(response)

        
        return str(response)
    
    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        return jsonify({"error": str(e)}), 500


    
    

@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        data = request.get_json()
        to_number = data.get('to')
        message_body = data.get('message')

        if not to_number or not message_body:
            return jsonify({'error': 'Faltan campos requeridos: to y message'}), 400
        
        # Agregar prefijo 'whatsapp:' 
        if not to_number.startswith('whatsapp:'):
            to_number = 'whatsapp:' + to_number
        
        from_number = 'whatsapp:' + os.getenv('TWILIO_SANDBOX_NUMBER') 

        message = client.messages.create(
            body=message_body,
            from_=from_number,
            to=to_number
        )

        logger.info(f"Mensaje enviado a {to_number}: {message_body}")

        # Guardar en la base de datos
        store_message(
            conversation_id=to_number,
            message_type='outgoing',
            content_text=message_body
        )

        return jsonify({'status': 'Mensaje enviado', 'sid': message.sid}), 200

    except Exception as e:
        logger.error(f"Error en /send_message: {e}")
        return jsonify({'error': str(e)}), 500
@app.route("/logs")
def get_logs():
    with open("app.log", "r") as f:
        content = f.read()
    return Response(content, mimetype="text/plain")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
