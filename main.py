from twilio.rest import Client
from flask import Flask, jsonify, request
import psycopg2
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
import os
import logging

# Cargar variables del .env
load_dotenv()

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

def store_message(conversation_id, message_type, content_text):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT * FROM cliente
            """
        )
        conn.commit()
        logger.info("Mensaje guardado en la base de datos")
    except Exception as e:
        logger.error(f"Error guardando mensaje: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

@app.route('/webhook', methods=['POST'])
def webhook():
    # Obtener datos del mensaje
    from_number = request.form.get('From')
    body = request.form.get('Body')

    print(f'Mensaje recibido de {from_number}: {body}')

    try:
        # Obtener datos del mensaje
        body = request.form.get('Body', '')
        from_number = request.form.get('From')
        
        logger.warning(f"Mensaje entrante {from_number}: msg: {body}")
        
        store_message(
            conversation_id=100,
            message_type='text',
            content_text=body
            )
        
        response = MessagingResponse()
        response.message(f"Hola, recibimos tu mensaje: {body}")
        
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
        
        message = client.messages.create(
            body=message_body,
            from_=os.getenv('TWILIO_PHONE_NUMBER'),
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



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
