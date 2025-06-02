import time
import logging
from dotenv import load_dotenv
import psycopg2
from typing import List, Dict, Any
from langchain.schema import Document
from langchain_chroma import Chroma

from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document



import os

from mensajeria import Mensajeria

logger = logging.getLogger(__name__)
load_dotenv()

class Embeddings:
    def __init__(self, persist_dir: str = "chroma_db",):
        self.persist_dir = persist_dir
        self.embeddings = OpenAIEmbeddings()
        self.embedding_data: List[Dict[str, Any]] = []
        self.vectorstore = None
        self.mensajeria = Mensajeria()
        
    def load_documents(self) -> List[Document]:
        try:
            conn = self.mensajeria.get_db_connection()
            cursor = conn.cursor()

            documents = []

            # Productos con precio más reciente
            cursor.execute("""
                SELECT p.id, p.nombre, p.descripcion, pr.valor
                FROM producto p
                LEFT JOIN LATERAL (
                    SELECT valor
                    FROM precio
                    WHERE producto_id = p.id
                    ORDER BY fecha_inicio DESC
                    LIMIT 1
                ) pr ON true
            """)

            rows = cursor.fetchall()
            for row in rows:
                documents.append(Document(
                    page_content=f"Producto: {row[1]}, Descripción: {row[2]}, Precio: {row[3] if row[3] is not None else 'N/A'}",
                    metadata={
                        "tipo": "producto",
                        "id": str(row[0]),
                        "nombre": row[1],
                        "descripcion": row[2],
                        "precio": float(row[3]) if row[3] is not None else None
                    }
                ))

            # Categorías
            cursor.execute("""
                SELECT id, nombre, descripcion
                FROM categoria
            """)

            rows = cursor.fetchall()
            for row in rows:
                documents.append(Document(
                    page_content=f"Categoría: {row[1]}, Descripción: {row[2]}",
                    metadata={
                        "tipo": "categoria",
                        "id": str(row[0]),
                        "nombre": row[1],
                        "descripcion": row[2]
                    }
                ))

            # Promociones con productos
            cursor.execute("""
                SELECT pr.id, pr.nombre, pr.descripcion, pr.fecha_inicio, pr.fecha_fin,
                       p.id as producto_id, p.nombre, p.descripcion, pp.descuento_porcentaje
                FROM promocion pr
                LEFT JOIN promo_producto pp ON pr.id = pp.promocion_id
                LEFT JOIN producto p ON pp.producto_id = p.id
            """)

            rows = cursor.fetchall()
            promociones_dict = {}

            for row in rows:
                promo_id = row[0]
                if promo_id not in promociones_dict:
                    promociones_dict[promo_id] = {
                        "nombre": row[1],
                        "descripcion": row[2],
                        "fecha_inicio": row[3],
                        "fecha_fin": row[4],
                        "productos": []
                    }
                if row[5]:  # id del producto
                    promociones_dict[promo_id]["productos"].append(
                        f"ID: {row[5]}, Producto: {row[6]}, Descripción: {row[7]}, Descuento: {row[8]}%"
                    )

            for promo_id, promo_data in promociones_dict.items():
                productos_texto = "\n".join(promo_data["productos"])
                contenido = f"Promoción: {promo_data['nombre']}, Descripción: {promo_data['descripcion']}, Vigencia: {promo_data['fecha_inicio']} a {promo_data['fecha_fin']}"
                if productos_texto:
                    contenido += f"\nProductos incluidos:\n{productos_texto}"

                documents.append(Document(
                    page_content=contenido,
                    metadata={
                        "tipo": "promocion",
                        "id": str(promo_id),
                        "nombre": promo_data['nombre'],
                        "descripcion": promo_data['descripcion'],
                        "fecha_inicio": str(promo_data['fecha_inicio']),
                        "fecha_fin": str(promo_data['fecha_fin'])
                    }
                ))

            cursor.close()
            conn.close()
            logger.info(f"Se cargaron {len(documents)} documentos desde la base de datos con precios, categorías y promociones")
            return documents

        except Exception as e:
            logger.error(f"Error al cargar documentos: {e}")
            return []



    def initialize(self) -> None:
        """Inicializa la base vectorial con Chroma desde documentos PostgreSQL."""
        logger.info("Iniciando generación y almacenamiento de embeddings")

        if os.path.exists(self.persist_dir) and os.listdir(self.persist_dir):
            logger.info("Cargando base vectorial existente")
            self.vectorstore = Chroma(
                persist_directory=self.persist_dir,
                embedding_function=self.embeddings
            )
            return

        documents = self.load_documents()

        if not documents:
            logger.warning("No se encontraron documentos para generar embeddings")
            return

        start_time = time.time()

        self.vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            persist_directory=self.persist_dir
        )
        

        logger.info(f"Base de datos vectorial creada en {time.time() - start_time:.2f} segundos")
        
    def search(self, query: str, k: int = 2) -> List[Dict[str, Any]]:
        """Realiza búsqueda por similitud con la query dada."""
        if not self.vectorstore:
            raise ValueError("Vector store not initialized. Call initialize() first.")
            
        start_time = time.time()
        docs = self.vectorstore.similarity_search(query, k=k)
        logger.info(f"Search completed in {time.time() - start_time:.2f} seconds")
        
        # Convertir documentos de LangChain a formato serializable
        results = []
        for i, doc in enumerate(docs, start=1):
            results.append({
                "id": i,
                "content": doc.page_content,
                "metadata": doc.metadata
            })
            
        return results
    def get_all_embeddings_as_text(self) -> str:
       
        if not self.vectorstore:
            raise ValueError("Vector store not initialized. Call initialize() first.")

        try:
            # Obtener los documentos reales (no cada letra)
            stored_data = self.vectorstore.get(include=["documents"])
            docs: List[str] = stored_data["documents"]  # Esto ya es una lista de strings

            return "\n\n".join(docs)  # Cada documento separado por doble salto de línea

        except Exception as e:
            logger.error(f"Error al obtener todos los embeddings como texto: {e}")
            return ""
    
    def get_all_documents_with_metadata(self) -> List[dict]:
        if not self.vectorstore:
            raise ValueError("Vector store not initialized. Call initialize() first.")

        try:
            stored_data = self.vectorstore.get(include=["documents", "metadatas"])
            docs: List[str] = stored_data["documents"]
            metadatas: List[dict] = stored_data["metadatas"]

            resultado = []

            for doc, metadata in zip(docs, metadatas):
                resultado.append({
                    "documento": doc,
                    "metadata": metadata
                })

            return resultado

        except Exception as e:
            logger.error(f"Error al obtener documentos con metadata: {e}")
            return []

        
        
    
    def rebuild_embeddings(self) -> None:
      
        logger.info("Reconstruyendo embeddings ")

       
        if os.path.exists(self.persist_dir):
            import shutil
            shutil.rmtree(self.persist_dir)
            logger.info(f"Directorio '{self.persist_dir}' eliminado.")

   
        documents = self.load_documents()
        if not documents:
            logger.warning("No se encontraron documentos para regenerar embeddings")
            return

        start_time = time.time()
        self.vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            persist_directory=self.persist_dir
        )
        logger.info(f"Embeddings reconstruidos en {time.time() - start_time:.2f} segundos.")
