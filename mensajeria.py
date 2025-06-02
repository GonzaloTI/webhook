import os
import psycopg2
from datetime import date
import logging

logger = logging.getLogger(__name__)


class Mensajeria:
    def __init__(self):
        self.conn = None

    def get_db_connection(self):
        if self.conn is None or self.conn.closed:
            try:
                self.conn = psycopg2.connect(
                    host=os.getenv('DB_HOST'),
                    port=os.getenv('DB_PORT'),
                    dbname=os.getenv('DB_NAME'),
                    user=os.getenv('DB_USER'),
                    password=os.getenv('DB_PASSWORD')
                )
            except Exception as e:
                logger.error(f"Conexión fallida Postgres: {e}")
                raise
        return self.conn

    def get_or_create_cliente_id(self, numero, nombre="desconocido"):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM cliente WHERE telefono = %s", (numero,))
            result = cursor.fetchone()
            if result:
                return result[0]
            else:
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

    def insertar_interes(self, cliente_id, producto_id=None, promocion_id=None, categoria_id=None, conversacion_id=None, nivel=0):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO interes (cliente_id, producto_id, promocion_id, categoria_id, nivel, conversacion_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (cliente_id, producto_id, promocion_id, categoria_id, nivel, conversacion_id))
            conn.commit()
            logger.info("Interés insertado correctamente.")
        except Exception as e:
            logger.error(f"Error al insertar interés: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

            
    def get_conversacion_id(self, cliente_id):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        try:
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

    def obtener_historial_conversacion(self,conversacion_id):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        historial_texto=""
        try:
            cursor.execute("""
                SELECT tipo, contenido_texto
                FROM mensaje
                WHERE conversacion_id = %s
                AND contenido_texto IS NOT NULL
                AND tipo IN ('text', 'ia')
                ORDER BY id DESC
            """, (conversacion_id,))
            historial = cursor.fetchall()

            historial_texto = "\n".join([
                f"Pregunta del cliente : '{fila[1]}'" if fila[0] == "text" else f"respuesta ia: '{fila[1]}'"
                for fila in historial if fila[1]
            ])

            logger.info("Historial de conversación:\n%s", historial_texto)
            return historial_texto

        except Exception as e:
            logger.error(f"Error al obtener historial: {e}")
            return ""
        finally:
            cursor.close()
            conn.close()
    def get_conversaciones_no_procesadas(self, cliente_id):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id FROM conversacion
                WHERE cliente_id = %s AND fecha = %s
                AND procesado = FALSE
                ORDER BY id DESC 
                """,
                (cliente_id, date.today())
            )
            resultados = cursor.fetchall()
            ids = [fila[0] for fila in resultados]
            return ids  # Lista de IDs
        except Exception as e:
            logger.error(f"Error al obtener conversaciones no procesadas: {e}")
            conn.rollback()
            return []
        finally:
            cursor.close()
            conn.close()
            
    def marcar_conversacion_como_procesada(self, conversacion_id: int):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE conversacion
                SET procesado = TRUE
                WHERE id = %s
                """,
                (conversacion_id,)
            )
            conn.commit()
            logger.info(f"Conversación {conversacion_id} marcada como procesada.")
        except Exception as e:
            logger.error(f"Error al marcar conversación como procesada: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()


    def store_message_twilio(self, conversation_id, response_ia):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO mensaje (
                    tipo, contenido_texto, media_url, media_mimetype,
                    media_filename, conversacion_id
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                ("ia", response_ia, None, None, None, conversation_id)
            )
            conn.commit()
            logger.info("Respuesta de IA guardada en la base de datos")
        except Exception as e:
            logger.error(f"Error guardando respuesta IA: {e}")
            conn.rollback()
        finally:
            cursor.close()

    def store_message(self, conversation_id, requestfull):
        conn = self.get_db_connection()
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
                ext = media_mimetype.split("/")[-1] if media_mimetype else "bin"
                media_filename = f"media.{ext}"

            cursor.execute(
                """
                INSERT INTO mensaje (
                    tipo, contenido_texto, media_url, media_mimetype,
                    media_filename, conversacion_id
                ) VALUES (%s, %s, %s, %s, %s, %s)
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

    def close(self):
        if self.conn:
            self.conn.close()
    def store_outgoing_message(self, conversation_id, content_text, media_url=None, media_mimetype=None, media_filename=None):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO mensaje (
                    tipo, contenido_texto, media_url, media_mimetype,
                    media_filename, conversacion_id
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    "outgoing",
                    content_text,
                    media_url,
                    media_mimetype,
                    media_filename,
                    conversation_id
                )
            )
            conn.commit()
            logger.info("Mensaje saliente guardado en la base de datos")
        except Exception as e:
            logger.error(f"Error guardando mensaje saliente: {e}")
            conn.rollback()
        finally:
            cursor.close()

