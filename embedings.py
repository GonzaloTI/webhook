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
        """Consulta la base de datos PostgreSQL y devuelve una lista de Document con nombre y descripción combinados."""
        try:
            conn = self.mensajeria.get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, nombre, descripcion
                FROM producto
            """)

            rows = cursor.fetchall()
            documents = [
                Document(
                    page_content=f"{row[1]}. {row[2]}",  # concatenar nombre y descripción
                    metadata={
                        "id": str(row[0]),
                        "nombre": row[1],
                        "descripcion": row[2]
                    }
                )
                for row in rows
            ]

            cursor.close()
            conn.close()
            logger.info(f" Se cargaron {len(documents)} documentos desde la base de datos")
            return documents

        except Exception as e:
            logger.error(f" Error al cargar documentos: {e}")
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