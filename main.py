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
from mensajeria import Mensajeria


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

            Normas:
            - Usa lenguaje útil, claro y amigable.
            - Responde en párrafos con saltos de línea para mejorar la legibilidad.
            - Si mencionas varios productos, usa listas con guiones.
            - No inventes productos ni características: responde solo con base en el catálogo proporcionado.
            - Si el mensaje es solo un saludo o una pregunta general, no menciones productos.
            - Usa el historial de conversación para mantener el contexto si es necesario.
            - sigue el contexto, ve si la pregunta anterior tiene que ver con la actual , si las preguntas anteriores se refieren a algun producto o promocion , reconoce que el nuevo ensaje esta relacionado con el anterior y basa tu respuesta en eso
            """

        user_prompt = f"""
            Contexto del cliente- historial de la conversación:
            {historial_texto}

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
        system_prompt = """
            -eres un analista para conmpletar mensaje o pregunta , basandote en el historial de la converzacion
            -si no hay nada en el historial devueves lo mismo que esta en "Nueva pregunta del cliente:"
           -si ves que si tiene relacion con la pregunta mas reciente hecha por el cliente concatenala y arma denuevo el mensaje o pregunta
           - si es algo fuera de contexto, solo devuelve lo mismo que esta en "Nueva pregunta del cliente:"
           - solo devueleve el mensaje reformulado, nada mas 
            """
        user_prompt = f"""
        
            Nueva pregunta del cliente:
                {question}
            
        
            Historial de conversación dividido por quien lo dijo [ cliente o la IA]:
            la primeras  del historial son la mas recientes .
            Historial:
            {historial_texto}
            ---aqui termina el historial------
                
            
            importante : Devuelve solo la pregunta reconstruida acorde al historial, sin explicaciones.
            
            importante , si ves que la pregunta no esta relacionada con el historial devuelva lo mismo que esta en " Nueva pregunta del cliente:"
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
      
        
        
        
        
def generate_banner_html_whit_intereses(cliente_id):
    try:
        import psycopg2
        import json

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
        ])
        logger.info(f"string para productosstr: {productos_str}")

        prompt_sistema = """
        Eres un asistente de análisis de intención en ventas de gafas.
        Recibes un historial de conversación con un catálogo de productos.
        Tu tarea es deducir a qué producto o intención se refiere el cliente.
        Responde con un JSON sin explicaciones.
        """

        prompt_usuario = f"""
        Historial de conversación:
        {historial_texto}

        Catálogo de productos:
        {productos_str}

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

 
@app.route('/analizarintenciones', methods=['POST'])
def analizar_intenciones():
    try:
        embeddings = Embeddings()
        embeddings.initialize()

        from_number = request.form.get('From')
        if not from_number:
            return jsonify({"status": "error", "message": "Número no proporcionado"}), 400

        numero = from_number.replace('whatsapp:', '')
     
        cliente_id = mensajeria.get_or_create_cliente_id(numero)
        conversacion_id = mensajeria.get_conversacion_id(cliente_id)
        historial_texto = mensajeria.obtener_historial_conversacion(conversacion_id=conversacion_id)
      
        Json_productos_promos_categorias = embeddings.get_all_documents_with_metadata()
     
        resultanalisis  = analizarintenciones( historial_texto,Json_productos_promos_categorias, cliente_id)
        
        for interes in resultanalisis.get("interes", []):
            tipo = interes.get("tipo")
            id_metadata = interes.get("id_metadata")
            nivel = interes.get("nivel_interes")
            # Asignar ID según tipo
            producto_id = id_metadata if tipo == "producto" else None
            promocion_id = id_metadata if tipo == "promocion" else None
            categoria_id = id_metadata if tipo == "categoria" else None

            # Insertar en la tabla de interés
            mensajeria.insertar_interes(
                cliente_id=cliente_id,
                producto_id=producto_id,
                promocion_id=promocion_id,
                categoria_id=categoria_id,
                nivel=nivel
            )       
        return jsonify({
            "status": "success",
            "cliente_id": cliente_id,
            "conversacion_id": conversacion_id,
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
        
        historial_texto = mensajeria.obtener_historial_conversacion(conversacion_id=get_converzacion_id)
        #logger.info(f"historial de converzacion : {historial_texto}")
        mensajeria.store_message(
            conversation_id=get_converzacion_id,
            requestfull= requestt
            )
        
        Productos_promos_categorias  = embedings.get_all_embeddings_as_text()
        #logger.warning(f"documentos de la bd : {Productos_promos_categorias}")
        
        newquestion = analyze_question( question=body, historial_texto= historial_texto)
        logger.warning(f"nueva pregunta segun el contexto  : {newquestion}")
        
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


@app.route('/generatepdfpersonalwhitenvio', methods=['POST'])
def generatepdfpersonalwhitenvio():
    try:
        data = request.get_json()
        numero = data.get("numero")

        if not numero:
            return jsonify({"error": "Faltan campos requeridos"}), 400

        cliente_id = mensajeria.get_or_create_cliente_id(numero)
        html = generate_banner_html_whit_intereses(cliente_id)

        # Generar el PDF con PDFShift
        try:
            response = requests.post(
                'https://api.pdfshift.io/v3/convert/pdf',
                headers={'X-API-Key': PDFSHIFT_API_KEY},
                json={
                    'source': html,
                    "landscape": False,
                    "use_print": False
                }
            )
            response.raise_for_status()
        except Exception as pdf_error:
            logger.error(f"Error generando PDF con PDFShift: {pdf_error}")
            return jsonify({"error": "No se pudo generar el PDF. Intenta más tarde."}), 500

        # Subir PDF a Cloudinary
        try:
            upload_result = cloudinary.uploader.upload_large(
                file=response.content,
                resource_type="raw",
                public_id=f"banner_pdf_{numero}"
            )
            media_url = upload_result["secure_url"]
        except Exception as cloudinary_error:
            logger.error(f"Error subiendo PDF a Cloudinary: {cloudinary_error}")
            return jsonify({"error": "Error al subir el PDF generado. Intenta más tarde."}), 500

        # Enviar mensaje WhatsApp con el PDF
        to_number = f"whatsapp:{numero}"
        from_number = f"whatsapp:{os.getenv('TWILIO_SANDBOX_NUMBER')}"

        try:
            message = client.messages.create(
                body="¡Aquí está tu banner personalizado en PDF!",
                from_=from_number,
                to=to_number,
                media_url=[media_url]
            )
        except Exception as twilio_error:
            logger.error(f"Error enviando PDF por WhatsApp: {twilio_error}")
            return jsonify({"error": "El PDF fue generado pero no se pudo enviar por WhatsApp."}), 500

        # Guardar en la BD solo si todo fue exitoso
        mensajeria.store_message(
            conversation_id=to_number,
            message_type='outgoing',
            content_text='Se envió el PDF personalizado por WhatsApp',
        )

        return jsonify({'status': 'PDF generado y enviado por WhatsApp', 'sid': message.sid}), 200

    except Exception as e:
        logger.error(f"Error general en /generatepdfpersonalwhitenvio: {e}")
        return jsonify({"error": str(e)}), 500





    
@app.route('/generatepdfpersonal', methods=['POST'])
def generatepdfpersonal():
    try:
        data = request.get_json()
       
        numero = data.get("numero")
        

        if not all([ numero]):
            return jsonify({"error": "Faltan campos requeridos"}), 400

        cliente_id = mensajeria.get_or_create_cliente_id(numero)
        
        
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
        mensajeria.store_message(
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
