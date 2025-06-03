from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
import smtplib
import requests
from twilio.rest import Client
from flask import Flask, Response, json, jsonify, request
import psycopg2
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
import os
import logging
from openai import OpenAI
import cloudinary
import cloudinary.uploader

from embedings import Embeddings
from generatehtml import GenerateHTML
from mensajeria import Mensajeria

email_user = os.getenv("EMAIL_USER")
email_pass = os.getenv("EMAIL_PASS")


load_dotenv()

client_opneai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PDFSHIFT_API_KEY = os.getenv("PDFSHIFT_API_KEY")

SCREENSHOTONE_API_KEY = os.getenv("SCREENSHOTONE_API_KEY")

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

mensajeria = Mensajeria()

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)
def generate_response_ia(question,historial_texto,productospromcat):
    
    try:
        
        
        system_prompt = """
            Eres un asistente de ventas de gafas se lo mas corto posible con la respuesta no inventes nada.

            Reglas:
            - Usa lenguaje simple, claro y amigable.
            - Responde en párrafos con saltos de línea para mejorar la legibilidad.
            - Si mencionas varios productos, usa listas con guiones.
            - No inventes productos ni características: responde solo con base en el catálogo proporcionado.
            - Si el mensaje es solo un saludo o una pregunta general, no menciones productos.
            - Usa el historial de conversación para mantener el contexto si es necesario.
              Eres un asistente de ventas especializado en gafas. Tu trabajo es responder de forma breve, clara y útil, sin inventar productos ni información.

            - Si mencionas productos, apóyate 100% en el catálogo proporcionado.
            - Mantén el contexto según el historial de conversación.
            - Si hay continuidad (por ejemplo: "y esas?", "cuánto cuestan?"), interpreta el contexto anterior.
            - Si el mensaje es genérico (ej: "hola", "buenas tardes"), responde cordialmente pero sin ofrecer productos.

            Solo responde si entiendes el contexto. Si no hay suficiente contexto, pide más información de forma cordial.
            """
        historial_conversacional=""    
            
        historial_lista = json.loads(historial_texto)

        # Luego haces el bucle normalmente
        for mensaje in historial_lista[::-1]:
            if mensaje["rol"] == "cliente":
                historial_conversacional += f"Cliente: {mensaje['contenido']}\n"
            else:
                historial_conversacional += f"Asistente: {mensaje['contenido']}\n"
        user_prompt = f"""
            Contexto del cliente- historial de la conversación:
            {historial_conversacional}

            Catálogo de productos:
            {productospromcat}

            Mensaje del cliente:
            {question}
            """

        # Llamada a OpenAI
        response = client_opneai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
                
            ],
                temperature=0.7, max_tokens=300
        )


        respuesta_texto = response.choices[0].message.content
        #print("Respuesta IA:", respuesta_texto)
        logger.info(f"Respuesta IA generada: {respuesta_texto}")
        return respuesta_texto

    except Exception as e:
        logger.error(f"Error en generate_response_ia: {e}")
        return "Lo siento, ocurrió un error al generar la respuesta."
    finally:
        pass
        
def analyze_question(question: str, historial_texto: str) -> str:
    try:
        
        historial_lista = json.loads(historial_texto)

        # Reordenamos: del más antiguo al más reciente
        historial_ordenado = historial_lista[::-1]

        # Formateamos el historial para el prompt
        historial_formateado = ""
        for mensaje in historial_ordenado:
            if mensaje["rol"] == "cliente":
                historial_formateado += f"Cliente: {mensaje['contenido']}\n"
            else:
                historial_formateado += f"Asistente: {mensaje['contenido']}\n"
                
        
        system_prompt = """
           Eres un reformulador de preguntas de cliente. Tu única tarea es reescribir la pregunta más reciente del cliente, basándote en el historial de conversación, si es necesario.

            Instrucciones estrictas:
            - No eres el asistente ni debes responder.
            - Si la pregunta es clara o no tiene relación con el historial, devuélvela sin modificar.
              - cuando es un saludo(hola, que tal, etc) o algo que no tiene que ver, solo devuelve lo mismo.
            - Si es ambigua ("¿y cuánto cuesta?", "¿dónde?", etc.), usa el historial para completar el contexto.
            - Nunca reescribas como si fueras la IA o con frases como "Te interesa..." o "Nuestro catálogo tiene...".
            - Devuelve **solo** la pregunta reformulada tal como la diría un cliente, no una respuesta.
            - NO agregues información, no digas "nosotros", ni menciones productos que no fueron mencionados antes.
            """

        user_prompt = f"""
        
        Historial (del más antiguo al más reciente):
            {historial_formateado}
            
            
        Nueva pregunta del cliente que se debe reformular segun el historial:
            {question}

            
            
            Recuerda: devuelve SOLO la pregunta reformulada, no respondas.
            
            IMPORTANTE:
            - Devuelve solamente la pregunta del cliente reescrita con contexto, como si fuera lo que el cliente quiso decir.
            - No respondas. No expliques. Solo devuelve la pregunta reformulada.
            Reglas:
            - (importante) los menajes que recibes son del cliente hacia el asistente de ventas.
             - cuando es un saludo(hola, que tal, etc) o algo que no tiene que ver, solo devuelve lo mismo.
            - Si el historial está vacío o no se relaciona con la pregunta, devuelve exactamente lo que está en "Nueva pregunta del cliente".
            - Si el nuevo mensaje del cliente es ambigua (por ejemplo: "¿y cuánto cuesta?"), usa el historial para completarla con contexto.
            - Solo devuelve el menasje reformulado , clara, sin explicaciones ni repeticiones.
            - Nunca inventes productos ni temas que no se mencionaron antes.
            
            """

        response = client_opneai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=100
        )

        reconstruida = response.choices[0].message.content.strip()
        logger.info(f"Pregunta reconstruida: {reconstruida}")
        return reconstruida

    except Exception as e:
        logger.error(f"Error en analyze_question: {e}")
        return "No se pudo analizar la pregunta."
      
        
        
        
        
def generate_banner_data_with_intereses(cliente_id):
    try:
        conn = mensajeria.get_db_connection()
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
                SELECT DISTINCT ON (producto_id) producto_id, valor
                FROM precio
                ORDER BY producto_id, fecha_inicio DESC
            ) pr ON pr.producto_id = p.id
            WHERE i.cliente_id = %s
              AND i.procesado = FALSE
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
                    SELECT p.nombre, pr.valor, pp.descuento_porcentaje, img.url
                    FROM promo_producto pp
                    JOIN producto p ON pp.producto_id = p.id
                    LEFT JOIN imagen img ON p.id = img.producto_id
                    LEFT JOIN (
                        SELECT DISTINCT ON (producto_id) producto_id, valor
                        FROM precio
                        ORDER BY producto_id, fecha_inicio DESC
                    ) pr ON pr.producto_id = p.id
                    WHERE pp.promocion_id = %s
                """, (promo_id,))

                productos_promo = cursor.fetchall()
                promo_items = [{
                    "nombre": p[0],
                    "precio": float(p[1]) if p[1] else None,
                    "descuento": float(p[2]) if p[2] is not None else None,
                    "imagen": p[3]
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
                    "descripcion": cat_desc,
                    "nivel": nivel
                })

        return {
            "cliente_id": cliente_id,
            "nombre": nombre,
            "telefono": numero,
            "intereses": intereses_info
        }

    except Exception as e:
        logger.error(f"Error generando datos de banner: {e}")
        return {"error": "Error generando datos de banner"}

        
    
    
@app.route('/initialize', methods=['POST'])
def initialize():
    try:
        embedings = Embeddings()
        embedings.initialize()

        resultados = embedings.search("gafas")
        for res in resultados:
            logger.warning(f"Content: {res['content']} - Metadata: {res['metadata']}")

        return jsonify({"status": "success", "results": resultados}), 200
    except Exception as e:
        logger.error(f"Error in /initialize: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
@app.route('/reload-embeddings', methods=['POST'])
def reload_embeddings():
    try:
        embeddings = Embeddings()
        embeddings.rebuild_embeddings()
        Productos_promos_categorias  = embeddings.get_all_embeddings_as_text()
           
        return jsonify({
            "status": "success",
            "message": "Embeddings recargados correctamente",
            "docuemntos": Productos_promos_categorias
        }), 200

    except Exception as e:
        logger.error(f"Error en /reload-embeddings: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error al recargar los embeddings: {str(e)}"
        }), 500
 
def analizarintenciones(historial_texto, Json_productos_promos_categorias, cliente_id):
    try:
        productos_str = "\n".join([
            ",".join(
                [f"Producto: {item.get('documento', '')}"] +
                [f"{k.capitalize()}: {v}" for k, v in item.get('metadata', {}).items()]
            )
            for item in Json_productos_promos_categorias
            if item.get('metadata', {}).get("tipo") == "producto"
        ])

        categorias_str = "\n".join([
            ",".join(
                [f"Categoría: {item.get('documento', '')}"] +
                [f"{k.capitalize()}: {v}" for k, v in item.get('metadata', {}).items()]
            )
            for item in Json_productos_promos_categorias
            if item.get('metadata', {}).get("tipo") == "categoria"
        ])

        promociones_str = "\n".join([
            ",".join(
                [f"Promoción: {item.get('documento', '')}"] +
                [f"{k.capitalize()}: {v}" for k, v in item.get('metadata', {}).items()]
            )
            for item in Json_productos_promos_categorias
            if item.get('metadata', {}).get("tipo") == "promocion"
        ])

        logger.info(f"string para productos_str: {productos_str}")
        logger.info(f"string para categorias_str: {categorias_str}")
        logger.info(f"string para promociones_str: {promociones_str}")

        prompt_sistema = """
        Eres un asistente de análisis de intención en ventas de gafas.
        Recibes un historial de conversación con un catálogo de productos , categorias y promociones(con su lista de productos).
        Tu tarea es deducir a qué producto o intención se refiere el cliente.
        Responde con un JSON sin explicaciones.
        """

        prompt_usuario = f"""
        Historial de conversación:
        {historial_texto}

        Catálogo de productos:
        {productos_str}
        
        
        Catalogo de categorias
        {categorias_str}
        
        Catalogo de promociones
        si el producto existe en la promocion, incluir la promocion igual.
        {promociones_str}

        Responde con un JSON que contenga un array de intereses detectados, donde cada interés debe incluir:
        - tipo: "producto", "categoria" o "promocion"
        - id_metadata: el id dentro del metadata
        - nivel_de_interes: entre 0 y 100
        
        Ejemplo de formato:
        {{
            "interes": [
                {{"tipo": "producto", "id_metadata": 5, "nivel_interes": 55}},
                {{"tipo": "producto", "id_metadata": 2, "nivel_interes": 90}}
            ]
        }}
        Solo responde con el JSON.
        """

        response = client_opneai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": prompt_usuario},
            ],
            temperature=0.4,
            max_tokens=500
        )

        resultado_texto = response.choices[0].message.content.strip()
        resultado_json = json.loads(resultado_texto)  # ← Este paso es clave
        return resultado_json

    except Exception as e:
        logger.error(f"Error en analizarintenciones(): {e}")
        return {"interes": []}  # Devolver un dict vacío por consistencia

@app.route('/clientes', methods=['GET'])
def obtener_clientes():
    try:
        lista_clientes = mensajeria.obtener_clientes_activos()
        return jsonify(lista_clientes), 200
    except Exception as e:
        logger.error(f"Error al obtener clientes: {e}")
        return jsonify({"error": "No se pudieron obtener los clientes"}), 500

 
@app.route('/analizarintenciones', methods=['POST'])
def analizar_intenciones():
    resultanalisis = []
    try:
        embeddings = Embeddings()
        embeddings.initialize()

        # Obtener datos desde JSON del cuerpo de la solicitud
        data = request.get_json()

        if not data or 'From' not in data:
            return jsonify({"error": "El campo 'From' es requerido"}), 400

        from_number = data['From']
        
        #from_number = request.form.get('From')
        
        if not from_number:
            return jsonify({"status": "error", "message": "Número no proporcionado"}), 400

        numero = from_number.replace('whatsapp:', '')
     
        cliente_id = mensajeria.get_or_create_cliente_id(numero)
        Json_productos_promos_categorias = embeddings.get_all_documents_with_metadata()
        
        conversaciones_ids = mensajeria.get_conversaciones_no_procesadas(cliente_id)
        logger.error(f"converzaciones no proc. : {conversaciones_ids}")
        
        resultados_analisis = []

        for conversacion_id in conversaciones_ids:
            logger.warning(f"Procesando conversación ID: {conversacion_id}") 
            historial_texto = mensajeria.obtener_historial_conversacion(conversacion_id=conversacion_id)

            resultanalisis = analizarintenciones(historial_texto, Json_productos_promos_categorias, cliente_id)
            resultados_analisis.append({
                "conversacion_id": conversacion_id,
                "analisis": resultanalisis
            })

            for interes in resultanalisis.get("interes", []):
                tipo = interes.get("tipo")
                id_metadata = interes.get("id_metadata")
                nivel = interes.get("nivel_interes")

                producto_id = id_metadata if tipo == "producto" else None
                promocion_id = id_metadata if tipo == "promocion" else None
                categoria_id = id_metadata if tipo == "categoria" else None

                mensajeria.insertar_interes(
                    cliente_id=cliente_id,
                    producto_id=producto_id,
                    promocion_id=promocion_id,
                    categoria_id=categoria_id,
                    conversacion_id=conversacion_id,
                    nivel=nivel
                )  
            mensajeria.marcar_conversacion_como_procesada(conversacion_id)
            
        return jsonify({
            "status": "success",
            "cliente_id": cliente_id,
            "conversaciones_ids": conversaciones_ids,
            "analisis" : resultanalisis
        }), 200

    except Exception as e:
        logger.error(f"Error en /analizarintenciones: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

 
 
    
@app.route('/webhook', methods=['POST'])
def webhook():
    embedings = Embeddings()
    embedings.initialize()
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
        
        cliente_id = mensajeria.get_or_create_cliente_id(numero)
        get_converzacion_id = mensajeria.get_conversacion_id(cliente_id)
        
        historial_texto = mensajeria.obtener_historial_conversacion(conversacion_id=get_converzacion_id,limite_pares=5)
        #logger.info(f"historial de converzacion : {historial_texto}")
        mensajeria.store_message(
            conversation_id=get_converzacion_id,
            requestfull= requestt
            )
        
        Productos_promos_categorias  = embedings.get_all_embeddings_as_text()
        #logger.warning(f"documentos de la bd : {Productos_promos_categorias}")
        
        newquestion = analyze_question( question=body, historial_texto= historial_texto)
        
        #newquestion =body
        
        logger.warning(f"nueva pregunta segun el contexto  : {newquestion}")
        
        #logger.warning(f"todos los embedings para enviarlo a la IA:{Productos_promos_categorias}")
        
        respuesta_ia =generate_response_ia(
            
            question=newquestion ,
            historial_texto= historial_texto,
            productospromcat=Productos_promos_categorias
            )
        
        if respuesta_ia:
            mensajeria.store_message_twilio(
                conversation_id=get_converzacion_id,
                response_ia=respuesta_ia
            )
        
        response = MessagingResponse()
        #response.message(f"Hola, recibimos tu mensaje: {respuesta_ia} , Conversacion id: {get_converzacion_id}")
        response.message("{respuesta_ia}")
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
    
    
    
@app.route('/generatepdfpersonal', methods=['POST'])
def generatepdfpersonal():
    try:
        data = request.get_json()
       
        numero = data.get("numero")
        nombre = data.get("nombre")
        correo = data.get("correo")
        

        if not nombre:
            return jsonify({"error": "Falta el nombre del cliente"}), 400
        if not numero and not correo:
            return jsonify({"error": "Debes proporcionar al menos un número o correo"}), 400

        cliente_id = mensajeria.get_or_create_cliente_id(numero)
        
        
        json = generate_banner_data_with_intereses(cliente_id)

        if not json.get("intereses"):
            return jsonify({"error": "No hay intereses disponibles para generar el banner."}), 400

        html= GenerateHTML(nombre=nombre)
        
        htmlresult = html.generate_banner(json)
        
        # Llamada a ScreenshotOne con contenido HTML
        screenshot_response = requests.get(
            "https://api.screenshotone.com/take",
            params={
                "access_key": SCREENSHOTONE_API_KEY,
                "html": htmlresult,
                "full_page": "true",
                "format": "jpeg"
            }
        )

        screenshot_response.raise_for_status()

        # 2. Guardar temporalmente la imagen
        temp_image_path = f"/tmp/banner_{numero}.jpg"
        with open(temp_image_path, "wb") as f:
            f.write(screenshot_response.content)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_id = f"banner_img_{numero}_{timestamp}"

        # 3. Subir imagen a Cloudinary
        try:
            upload_result = cloudinary.uploader.upload(
                temp_image_path,
                resource_type="image",
                public_id=unique_id
            )
            
            media_url = upload_result["secure_url"]
        except Exception as cloudinary_error:
            logger.error(f"Error subiendo imagen a Cloudinary: {cloudinary_error}")
            return jsonify({"error": "Error al subir la imagen generada. Intenta más tarde."}), 500

        # 4. Enviar imagen por WhatsApp con Twilio
        if numero:
            to_number = f"whatsapp:{numero}"
            from_number = f"whatsapp:{os.getenv('TWILIO_SANDBOX_NUMBER')}"
            try:
                message = client.messages.create(
                    body="¡Tenemos estas ofertas para Ti!",
                    from_=from_number,
                    to=to_number,
                    media_url=[media_url]
                )
            except Exception as twilio_error:
                logger.error(f"Error enviando imagen por WhatsApp: {twilio_error}")
                return jsonify({"error": "La imagen fue generada pero no se pudo enviar por WhatsApp."}), 500

        #4.2 si hay correo enviar por correo 
        if correo:
            msg = EmailMessage()
            msg['Subject'] = '🎉 tenemos Porductos que te podrian interesar a Ti'
            msg['From'] = formataddr(('Soporte', email_user))
            msg['To'] = correo
            msg.set_content("Hola,\n\nAquí tienes algunas de nuestra ofertas que te podrían interesar a ti. ¡Gracias por tu interés!")

            with open(temp_image_path, 'rb') as img:
                img_data = img.read()
                msg.add_attachment(
                    img_data,
                    maintype='image',
                    subtype='jpeg',
                    filename=f"banner_{numero}.jpg"
                )

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(email_user, email_pass)
                smtp.send_message(msg)



        # 5. Guardar el mensaje en la base de datos
        conversacion_id = mensajeria.get_conversacion_id(cliente_id)
        mensajeria.store_outgoing_message(
            conversation_id=conversacion_id,
            content_text="Se envió el banner personalizado por WhatsApp",
            media_url=media_url,
            media_mimetype="image/jpeg",
            media_filename=f"banner_img_{numero}.jpg"
        )
        
        mensajeria.marcar_interes_como_procesado(cliente_id=cliente_id, medio="correo,twilio")

        return jsonify({'status': 'Imagen generada y enviada por WhatsApp', 'sid': message.sid}), 200


    except Exception as e:
        logger.error(f"Error general en /generateimagepersonalwhitenvio: {e}")
        return jsonify({"error": str(e)}), 500



@app.route('/generateimagepersonalwithemail', methods=['POST'])
def generateimagepersonalwithemail():
    try:
        data = request.get_json()
        numero = data.get("numero")
        correo = data.get("correo")
        nombre = data.get("nombre")

        if not numero or not correo or not nombre:
            return jsonify({"error": "Número, nombre o correo faltante"}), 400

        cliente_id = mensajeria.get_or_create_cliente_id(numero)
        json = generate_banner_data_with_intereses(cliente_id)
        
        if not json.get("intereses"):
            return jsonify({"error": "No hay intereses disponibles para generar el banner."}), 400

        html = GenerateHTML(nombre=nombre)
        html_result = html.generate_banner(json)

        screenshot_response = requests.get(
            "https://api.screenshotone.com/take",
            params={
                "access_key": SCREENSHOTONE_API_KEY,
                "html": html_result,
                "full_page": "true",
                "format": "jpeg"
            }
        )
        screenshot_response.raise_for_status()

        # Guardar imagen temporal
        temp_image_path = f"/tmp/banner_{numero}.jpg"
        with open(temp_image_path, "wb") as f:
            f.write(screenshot_response.content)

        # Subir a Cloudinary (opcional, por si también quieres registro en BD)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_id = f"banner_email_{numero}_{timestamp}"

        upload_result = cloudinary.uploader.upload(
            temp_image_path,
            resource_type="image",
            public_id=unique_id
        )
        media_url = upload_result["secure_url"]


        msg = EmailMessage()
        msg['Subject'] = '🎉 tenemos Porductos que te podrian interesar a Ti'
        msg['From'] = formataddr(('Soporte', email_user))
        msg['To'] = correo
        msg.set_content("Hola,\n\nAquí tienes tu banner personalizado. ¡Gracias por tu interés!")

        with open(temp_image_path, 'rb') as img:
            img_data = img.read()
            msg.add_attachment(
                img_data,
                maintype='image',
                subtype='jpeg',
                filename=f"banner_{numero}.jpg"
            )

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(email_user, email_pass)
            smtp.send_message(msg)

        # Registrar en la base de datos
        conversacion_id = mensajeria.get_conversacion_id(cliente_id)
        mensajeria.store_outgoing_message(
            conversation_id=conversacion_id,
            content_text="Se envió el banner personalizado por correo electrónico",
            media_url=media_url,
            media_mimetype="image/jpeg",
            media_filename=f"banner_{numero}.jpg"
        )
        mensajeria.marcar_interes_como_procesado(cliente_id=cliente_id, medio="correo,twilio")

        return jsonify({'status': 'Imagen enviada correctamente por correo'}), 200

    except Exception as e:
        logger.error(f"Error en /generateimagepersonalwithemail: {e}")
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
        numero = to_number.replace('whatsapp:', '')  
        cliente_id = mensajeria.get_or_create_cliente_id(numero)
        conversacion_id = mensajeria.get_conversacion_id(cliente_id)

        mensajeria.store_outgoing_message(
            conversation_id=conversacion_id,
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
