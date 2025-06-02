import random


class GenerateHTML:
    def __init__(self, nombre, productos=None, categorias=None, promociones=None):
        self.nombre = nombre
        self.productos = productos or []
        self.categorias = categorias or []
        self.promociones = promociones or []
                
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
                        }}
                        .card {{ opacity: 0.95; }}
                    </style>
                </head>
                <body>
                <div class=\"container bg-dark bg-opacity-75 p-5 rounded shadow-lg\">
                    <div class=\"text-center mb-5\">
                        <h1 class=\"display-4 text-warning fw-bold\">¡Hola, nombrepersona !</h1>
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
                    <title>Bienvenido {{nombre}}</title>
                    <link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css\" rel=\"stylesheet\">
                    <style>
                        body {{
                            background-color: #fff8e1;
                            padding: 30px;
                            font-family: sans-serif;
                        }}
                    </style>
                </head>
                <body>
                <div class=\"container border border-warning p-4 bg-light rounded\">
                    <div class=\"text-center mb-3\">
                        <h1 class=\"text-warning\">¡Bienvenido {{nombre}}!</h1>
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


    def generate_banner(self):
        productos_html = ""
        if self.productos:
            productos_html += "<h3 class='mt-4'>Productos recomendados:</h3><div class='row'>"
            for i, prod in enumerate(self.productos):
                productos_html += f"""
                <div class=\"col-md-6 mb-3\">
                    <div class=\"card\">
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
                categorias_html += f"<li class='list-group-item'>{cat}</li>"
            categorias_html += "</ul>"

        promociones_html = ""
        if self.promociones:
            promociones_html += "<h3 class='mt-4'>Promociones especiales:</h3><ul class='list-group'>"
            for promo in self.promociones:
                promociones_html += f"<li class='list-group-item text-danger fw-bold'>{promo}</li>"
            promociones_html += "</ul>"

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
