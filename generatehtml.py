import random


class GenerateHTML:
    def __init__(self, nombre):
        self.nombre = nombre

        self.plantillas = [
            (
                f"""
                <!DOCTYPE html>
                <html lang=\"es\">
                <head>
                    <meta charset=\"UTF-8\">
                    <title>Banner Publicitario</title>
                    <link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css\" rel=\"stylesheet\">
                    <style>
                        body {{
                            background-image: url('https://www.lafam.com.co/cdn/shop/files/front-0RX7230__5204__P21__shad__al2_704x480.jpg');
                            background-size: cover;
                            background-position: center;
                            background-repeat: no-repeat;
                            min-height: 100vh;
                            padding: 40px;
                            color: white;
                            backdrop-filter: brightness(0.8);
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            text-align: center;
                        }}
                        .container {{
                            max-width: 960px;
                            background-color: rgba(0, 0, 0, 0.75);
                            padding: 2rem;
                            border-radius: 15px;
                        }}
                        .card {{ opacity: 0.95; }}
                    </style>
                </head>
                <body>
                <div class=\"container shadow-lg\">
                    <div class=\"text-center mb-5\">
                        <h1 class=\"display-4 text-warning fw-bold\">¡Hola, nombrepersona!</h1>
                        <p class=\"lead text-light\">Tenemos algo increíble pensado para ti 👇</p>
                    </div>
                """,
                """
                    <div class=\"text-center mt-5\">
                        <p class=\"text-light\">📞 Contáctanos para más información o pedidos</p>
                    </div>
                </div>
                </body>
                </html>
                """
            ),
            (
                f"""
                <!DOCTYPE html>
                <html lang=\"es\">
                <head>
                    <meta charset=\"UTF-8\">
                    <title>Hola denuevo  nombrepersona</title>
                    <link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css\" rel=\"stylesheet\">
                    <style>
                        body {{
                            background-color: #fff8e1;
                            padding: 30px;
                            font-family: sans-serif;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            text-align: center;
                        }}
                        .container {{
                            max-width: 960px;
                        }}
                    </style>
                </head>
                <body>
                <div class=\"container border border-warning p-4 bg-light rounded\">
                    <div class=\"text-center mb-3\">
                        <h1 class=\"text-warning\">Hola denuevo  nombrepersona !</h1>
                        <p class=\"text-muted\">Explora nuestras increíbles ofertas:</p>
                    </div>
                """,
                """
                    <div class=\"text-center mt-4\">
                        <p class=\"text-muted\">📩 Escríbenos si deseas más detalles o ayuda</p>
                    </div>
                </div>
                </body>
                </html>
                """
            )
        ]

    def generate_banner(self, datasjon):
        self.nombre = datasjon.get("nombre", self.nombre)
        intereses = datasjon.get("intereses", [])
        self.productos = [i for i in intereses if i.get("tipo") == "producto"]
        self.promociones = [i for i in intereses if i.get("tipo") == "promocion"]
        self.categorias = [i for i in intereses if i.get("tipo") == "categoria"]

        productos_html = ""
        if self.productos:
            productos_html += "<h3 class='mt-4'>Productos recomendados:</h3><div class='row justify-content-center'>"
            for prod in self.productos:
                productos_html += f"""
                <div class=\"col-md-6 mb-3\">
                    <div class=\"card\">
                        <img src=\"{prod.get('imagen', '')}\" class=\"card-img-top\" alt=\"Imagen del producto\">
                        <div class=\"card-body\">
                            <h5 class=\"card-title\">{prod.get("nombre", "Producto")}</h5>
                            <p class=\"card-text\">{prod.get("descripcion", "")}</p>
                            <p class=\"card-text fw-bold text-success\">Precio: ${prod.get("precio", "0.00")}</p>
                        </div>
                    </div>
                </div>
                """
            productos_html += "</div>"

        categorias_html = ""
        if self.categorias:
            categorias_html += "<h3 class='mt-4'>Categorías destacadas:</h3><ul class='list-group'>"
            for cat in self.categorias:
                categorias_html += f"<li class='list-group-item'><strong>{cat.get('nombre')}</strong>: {cat.get('descripcion')}</li>"
            categorias_html += "</ul>"

        promociones_html = ""
        if self.promociones:
            promociones_html += "<h3 class='mt-4'>Promociones especiales:</h3><div class='row justify-content-center'>"
            for promo in self.promociones:
                promociones_html += f"""
                <div class='col-md-6 mb-3'>
                    <div class='card border-danger'>
                        <div class='card-body'>
                            <h5 class='card-title text-danger'>{promo.get("nombre", "Promoción")}</h5>
                """
                for producto in promo.get("productos", []):
                    promociones_html += f"""
                        <p class='card-text'>
                            <img src='{producto.get("imagen", "")}' width='50'>
                            {producto.get("nombre")}, Precio: ${producto.get("precio")}, Descuento: {producto.get("descuento")}%
                        </p>
                    """
                promociones_html += "</div></div></div>"
            promociones_html += "</div>"

        superior, inferior = random.choice(self.plantillas)
        superior = superior.replace("nombrepersona", self.nombre)

        html = f"""
        {superior}
        {productos_html}
        {categorias_html}
        {promociones_html}
        {inferior}
        """

        return html.strip()
