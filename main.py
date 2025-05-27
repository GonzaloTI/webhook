import requests
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

PDFSHIFT_API_KEY = os.getenv("PDFSHIFT_API_KEY")

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
        
def generate_banner_html_whit_intereses(cliente_id):
    try:
        import psycopg2
        import json

        conn = get_db_connection()
        cursor = conn.cursor()

        # Obtener nombre y número del cliente
        cursor.execute("SELECT nombre, telefono FROM cliente WHERE id = %s", (cliente_id,))
        cliente = cursor.fetchone()
        if not cliente:
            raise Exception("Cliente no encontrado")
        nombre, numero = cliente

        # Obtener intereses
        cursor.execute("""
            SELECT i.producto_id, i.promocion_id, i.categoria_id, i.nivel,
                   p.nombre, p.descripcion, img.url, pr.valor
            FROM interes i
            LEFT JOIN producto p ON i.producto_id = p.id
            LEFT JOIN imagen img ON p.id = img.producto_id
            LEFT JOIN (
                SELECT producto_id, valor
                FROM precio
                ORDER BY fecha_inicio DESC
            ) pr ON pr.producto_id = p.id
            WHERE i.cliente_id = %s
            LIMIT 10;
        """, (cliente_id,))
        intereses = cursor.fetchall()

        intereses_info = []

        for row in intereses:
            producto_id, promo_id, cat_id, nivel, prod_nombre, prod_desc, img_url, precio = row
            if producto_id:
                intereses_info.append({
                    "tipo": "producto",
                    "nombre": prod_nombre,
                    "descripcion": prod_desc,
                    "precio": float(precio) if precio else None,
                    "imagen": img_url,
                    "nivel": nivel
                })
            elif promo_id:
                
                cursor.execute("SELECT nombre FROM promocion WHERE id = %s", (promo_id,))
                promo_data = cursor.fetchone()
                promo_nombre = promo_data[0] if promo_data else f"Promoción {promo_id}"

                cursor.execute("""
                    SELECT p.nombre, pr.valor, pp.descuento_porcentaje
                    FROM promo_producto pp
                    JOIN producto p ON pp.producto_id = p.id
                    LEFT JOIN (
                        SELECT producto_id, valor
                        FROM precio
                        ORDER BY fecha_inicio DESC
                    ) pr ON pr.producto_id = p.id
                    WHERE pp.promocion_id = %s
                """, (promo_id,))
                
                
                productos_promo = cursor.fetchall()
                promo_items = [{
                    "nombre": p[0],
                    "precio": float(p[1]) if p[1] else None,
                    "descuento": float(p[2]) if p[2] is not None else None
                } for p in productos_promo]

                intereses_info.append({
                    "tipo": "promocion",
                    "id": promo_id,
                    "nombre": promo_nombre,
                    "productos": promo_items,
                    "nivel": nivel
                })
            elif cat_id:
    
                cursor.execute("SELECT nombre, descripcion FROM categoria WHERE id = %s", (cat_id,))
                cat_data = cursor.fetchone()
                cat_nombre = cat_data[0] if cat_data else f"Categoría {cat_id}"
                cat_desc = cat_data[1] if cat_data else None
                intereses_info.append({
                    "tipo": "categoria",
                    "id": cat_id,
                    "nombre": cat_nombre,
                    "descripcion":cat_desc,
                    "nivel": nivel
                })

        # Convertir los intereses en texto
        descripciones = []
        for interes in intereses_info:
            if interes["tipo"] == "producto":
                texto = f"Interesado en el producto: '{interes['nombre']}' ({interes['descripcion']}), precio: ${interes['precio']}, imagen: {interes['imagen']}."
            elif interes["tipo"] == "promocion":
                productos_txt = ", ".join([
                    f" :{p['nombre']} (${p['precio']})" + 
                    (f" con {p['descuento']}% de descuento" if p.get("descuento") else "")
                    for p in interes["productos"]
                ])
                texto = f"Interesado en la promoción: ' Promocion:{interes['nombre']}' con productos: {productos_txt}."
            elif interes["tipo"] == "categoria":
                 texto = f"Interesado en productos de la categoría: ' Categoria: {interes['nombre']}' ({interes['descripcion']})."
            descripciones.append(texto)
            
            
        preferencias_texto = "\n".join(descripciones)


        logger.critical(f"todo el texto de los intereces {preferencias_texto}.")  # Log del resultaod de intereces



        # Prompt con intereses como texto
        prompt = f"""
        Eres un generador de contenido HTML para campañas publicitarias personalizadas.

         Tu tarea:
        Generar un HTML de banner publicitario dirigido a un cliente llamado **{nombre}**, con número de contacto **{numero}**, y con las siguientes preferencias:\n{preferencias_texto}

         Instrucciones de como armar el html:
        - El HTML debe ser compatible con PDFShift.
        - Usa Bootstrap desde un CDN para aplicar estilos. Incluye este enlace en el <head>:
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        - Usa clases de Bootstrap para los estilos (no uses CSS personalizado ni <style>).
        - No uses JavaScript.
        - Ponle con Bootstrap mucho color , color de fondo, estilos con Bootstrap a las letras, que parezca una folleto publicitario.
        - obligatorio poner fondo de la pagina de algun color segun veas la categoria que se tene de preferencia con boottrap.
        - si hay productos de promocion, has una lista de esas promociones de 2 columnas en cards de colores.
        - si hay categorias de preferencia, has cards de cada categoria.
        - Debe parecer un anuncio llamativo o banner publicitario.
        - Incluir un título atractivo y personalizado para {nombre}.
        - Mostrar un mensaje principal conectado con sus intereses.
        - si no hay preferencias , solo muestra algo vacio diciendo no tiene preferencias.
        - hay tres secciones , si es que hay interes de: productos, promociones y de categorías , 
        - Incluir imágenes con URLs de ejemplo si no se tienen.
        - No ocupe ni inventes ningun producto o categoria, solo usa lo que te pase.
        - Incluir al final un texto de contacto con la tienda +591 12345678.
        

         Responde únicamente con el HTML completo, sin explicaciones ni comentarios.
        """

        response = client_opneai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un generador de banners en HTML para marketing digital."},
                {"role": "user", "content": prompt}
            ]
        )

        html_result = response.choices[0].message.content
        logger.info(f"HTML generado para {nombre}: {html_result[:80]}...")  # Log parcial
        return html_result

    except Exception as e:
        logger.error(f"Error generando banner: {e}")
        return "<html><body><h1>Error generando banner</h1></body></html>"
       
        
        
        
        
        
def generate_banner_html(nombre, numero, preferencias):
    try:
        
        prompt = f"""
            Eres un generador de contenido HTML para campañas publicitarias personalizadas.

            🎯 Tu tarea:
            Generar un HTML de banner publicitario dirigido a un cliente llamado **{nombre}**, con número de contacto **{numero}**, y con las siguientes preferencias: **{preferencias}**.

            ✅ Requisitos:
            - El HTML debe ser compatible con PDFShift.
            - Usa Bootstrap desde un CDN para aplicar estilos. Incluye este enlace en el <head>:
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            - Usa clases de Bootstrap para los estilos (no uses CSS personalizado ni <style>).
            - No uses JavaScript.
            - Ponle con Bootstrap mucho color , color de fondo, estilos con Bootstrap a las letras, queparezca una folleto publicitario
            - Debe parecer un anuncio llamativo o banner publicitario.
            - Incluir un título atractivo y personalizado para {nombre}.
            - Mostrar un mensaje principal conectado con sus intereses.
            - Agregar 2 a 3 ofertas relevantes basadas en las preferencias.
            - Incluir imágenes con URLs de ejemplo como: https://www.lafam.com.co/cdn/shop/files/front-0RX7230__5204__P21__shad__al2_704x480.jpg.
            - Incluir al final un texto de contacto con el número: **{numero}**.

            📦 Responde únicamente con el HTML completo, sin explicaciones ni comentarios.

            📄 Estructura esperada:
            <html>
            <head>...</head>
            <body>...</body>
            </html>
            """


       

        response = client_opneai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un generador de banners en HTML para marketing digital."},
                {"role": "user", "content": prompt}
            ]
        )

        html_result = response.choices[0].message.content
        logger.info(f"HTML generado para {nombre}: {html_result[:80]}...")  # Log parcial
        return html_result

    except Exception as e:
        logger.error(f"Error generando banner: {e}")
        return "<html><body><h1>Error generando banner</h1></body></html>"


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

@app.route('/testjson', methods=['POST'])
def test_json():
    try:
        data = request.get_json(force=True)
        print("Datos recibidos:", data)
        return jsonify({"recibido": data}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    
@app.route('/generatepdf', methods=['POST'])
def generate_pdf():
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido o Content-Type incorrecto"}), 400
        data = request.get_json()
        nombre = data.get("nombre")
        numero = data.get("numero")
        preferencias = data.get("preferencias")

        if not all([nombre, numero, preferencias]):
            return jsonify({"error": "Faltan campos requeridos"}), 400

        html = generate_banner_html(nombre, numero, preferencias)
        
       
        print(html)  # Quitar en producción
        
        return (html, 200, {'Content-Type': 'text/html'})

        response = requests.post(
            'https://api.pdfshift.io/v3/convert/pdf',
            headers={ 'X-API-Key': PDFSHIFT_API_KEY },
            json={ 'source': html,
                    "landscape": False,
                    "use_print": False}
        )


        response.raise_for_status()

        return (response.content, 200, {
            'Content-Type': 'application/pdf',
            'Content-Disposition': 'inline; filename="banner.pdf"'
        })

    except Exception as e:
        return jsonify({"error trycatch": str(e)}), 500


    
@app.route('/generatepdfpersonal', methods=['POST'])
def generatepdfpersonal():
    try:
        data = request.get_json()
       
        numero = data.get("numero")
        

        if not all([ numero]):
            return jsonify({"error": "Faltan campos requeridos"}), 400

        cliente_id = get_or_create_cliente_id(numero)
        
        
        html = generate_banner_html_whit_intereses(cliente_id)

        #print(html)  # Quitar en producción
        
        #return (html, 200, {'Content-Type': 'text/html'})

        response = requests.post(
            'https://api.pdfshift.io/v3/convert/pdf',
            headers={ 'X-API-Key': PDFSHIFT_API_KEY },
            json={ 'source': html,
                    "landscape": False,
                    "use_print": False}
        )


        response.raise_for_status()

        return (response.content, 200, {
            'Content-Type': 'application/pdf',
            'Content-Disposition': 'inline; filename="banner.pdf"'
        })

    except Exception as e:
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
