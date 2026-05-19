"""
Script para poblar la base de datos con datos de demostración.

Ejecutar desde la carpeta `backend`:

    python seed_data.py            # Modo seguro: solo crea/actualiza los datos demo.
                                   # No toca usuarios ni libros creados por personas reales.
    python seed_data.py --reset    # Borra TODO (usuarios y libros) y re-siembra desde cero.

Los registros demo se marcan con `is_demo: True` para poder distinguirlos
de los datos creados por usuarios reales de la plataforma.
"""
import argparse
import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.utils.auth import hash_password

BOOK_IMAGES = [
    "https://images.unsplash.com/photo-1544947950-fa07a98d237f?w=600&q=80",
    "https://images.unsplash.com/photo-1512820790803-83ca734da794?w=600&q=80",
    "https://images.unsplash.com/photo-1495446815901-a7297e633e8d?w=600&q=80",
    "https://images.unsplash.com/photo-1524995995642-b05b365c168d?w=600&q=80",
    "https://images.unsplash.com/photo-1476275466078-4007374efbbe?w=600&q=80",
    "https://images.unsplash.com/photo-1589998059174-4d881ffd2f96?w=600&q=80",
    "https://images.unsplash.com/photo-1543002588-bfa74002ed7e?w=600&q=80",
    "https://images.unsplash.com/photo-1481627834876-b7833e8f5570?w=600&q=80",
    "https://images.unsplash.com/photo-1516979186334-10f778a39e8a?w=600&q=80",
    "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=600&q=80",
]

# Libros demo. Índice del libro = posición en esta lista.
SEED_BOOKS = [
    # 0-9: catálogo base
    ("Cien años de soledad", "Gabriel García Márquez", 450.0, "nuevo", "La Habana", "Centro Habana"),
    ("El hombre que calculaba", "Malba Tahan", 280.0, "usado", "La Habana", "Plaza de la Revolución"),
    ("Ficciones", "Jorge Luis Borges", 320.0, "usado", "Santiago de Cuba", "Santiago de Cuba"),
    ("La Edad de Oro", "José Martí", 150.0, "usado", "Matanzas", "Matanzas"),
    ("Breve historia del tiempo", "Stephen Hawking", 500.0, "nuevo", "Villa Clara", "Santa Clara"),
    ("El Principito", "Antoine de Saint-Exupéry", 200.0, "usado", "Holguín", "Holguín"),
    ("1984", "George Orwell", 380.0, "usado", "Camagüey", "Camagüey"),
    ("Historia de Cuba", "Eduardo Torres Cuevas", 420.0, "nuevo", "Cienfuegos", "Cienfuegos"),
    ("Matemáticas 10mo grado", "Editorial Pueblo y Educación", 180.0, "usado", "Las Tunas", "Las Tunas"),
    ("Don Quijote de la Mancha", "Miguel de Cervantes", 550.0, "nuevo", "Pinar del Río", "Pinar del Río"),
    # 10-12: ampliación Librería La Habana
    ("Paradiso", "José Lezama Lima", 480.0, "nuevo", "La Habana", "Habana Vieja"),
    ("Los pasos perdidos", "Alejo Carpentier", 420.0, "usado", "La Habana", "Diez de Octubre"),
    ("El hombre que amaba a los perros", "Leonardo Padura", 550.0, "nuevo", "La Habana", "Centro Habana"),
    # 13-15: ampliación Libros del Oriente
    ("Rayuela", "Julio Cortázar", 460.0, "usado", "Santiago de Cuba", "Palma Soriano"),
    ("La ciudad y los perros", "Mario Vargas Llosa", 400.0, "usado", "Santiago de Cuba", "Contramaestre"),
    ("Pedro Páramo", "Juan Rulfo", 350.0, "nuevo", "Santiago de Cuba", "Songo-La Maya"),
    # 16-17: ampliación Tienda Central
    ("Física 11mo grado", "Editorial Pueblo y Educación", 200.0, "usado", "Cienfuegos", "Cienfuegos"),
    ("Química 12mo grado", "Editorial Pueblo y Educación", 220.0, "nuevo", "Sancti Spíritus", "Sancti Spíritus"),
    # 18-23: Librería Vueltabajo (Pinar del Río)
    ("La Ilíada", "Homero", 380.0, "usado", "Pinar del Río", "Pinar del Río"),
    ("La Odisea", "Homero", 380.0, "usado", "Pinar del Río", "Pinar del Río"),
    ("Hamlet", "William Shakespeare", 300.0, "usado", "Pinar del Río", "Viñales"),
    ("Romeo y Julieta", "William Shakespeare", 280.0, "usado", "Pinar del Río", "Viñales"),
    ("Crimen y castigo", "Fiódor Dostoyevski", 520.0, "nuevo", "Pinar del Río", "Pinar del Río"),
    ("Los hermanos Karamázov", "Fiódor Dostoyevski", 600.0, "nuevo", "Pinar del Río", "Pinar del Río"),
    # 24-29: Atenas Libros (Matanzas)
    ("Cecilia Valdés", "Cirilo Villaverde", 410.0, "usado", "Matanzas", "Matanzas"),
    ("Sab", "Gertrudis Gómez de Avellaneda", 360.0, "usado", "Matanzas", "Cárdenas"),
    ("Espejo de paciencia", "Silvestre de Balboa", 320.0, "usado", "Matanzas", "Cárdenas"),
    ("Versos sencillos", "José Martí", 220.0, "nuevo", "Matanzas", "Matanzas"),
    ("Ismaelillo", "José Martí", 180.0, "nuevo", "Matanzas", "Matanzas"),
    ("La isla en peso", "Virgilio Piñera", 390.0, "usado", "Matanzas", "Jovellanos"),
    # 30-35: Librería Agramonte (Camagüey)
    ("El amor en los tiempos del cólera", "Gabriel García Márquez", 470.0, "nuevo", "Camagüey", "Camagüey"),
    ("Crónica de una muerte anunciada", "Gabriel García Márquez", 350.0, "usado", "Camagüey", "Camagüey"),
    ("El otoño del patriarca", "Gabriel García Márquez", 420.0, "usado", "Camagüey", "Florida"),
    ("El Aleph", "Jorge Luis Borges", 310.0, "usado", "Camagüey", "Nuevitas"),
    ("La invención de Morel", "Adolfo Bioy Casares", 280.0, "nuevo", "Camagüey", "Camagüey"),
    ("Memorias del subdesarrollo", "Edmundo Desnoes", 250.0, "usado", "Camagüey", "Camagüey"),
    # 36-41: Holguín Lecturas
    ("Tres tristes tigres", "Guillermo Cabrera Infante", 480.0, "nuevo", "Holguín", "Holguín"),
    ("La Habana para un infante difunto", "Guillermo Cabrera Infante", 510.0, "usado", "Holguín", "Holguín"),
    ("Diccionario español-inglés", "Larousse", 400.0, "usado", "Holguín", "Banes"),
    ("Atlas del mundo", "National Geographic", 650.0, "nuevo", "Holguín", "Banes"),
    ("Anatomía humana", "Editorial Médica Panamericana", 850.0, "nuevo", "Holguín", "Holguín"),
    ("Manual de Python básico", "Editorial Académica", 700.0, "nuevo", "Holguín", "Mayarí"),
    # 42-49: Bayamo Lecturas (Granma)
    ("Celestino antes del alba", "Reinaldo Arenas", 380.0, "usado", "Granma", "Bayamo"),
    ("Antes que anochezca", "Reinaldo Arenas", 420.0, "usado", "Granma", "Bayamo"),
    ("La consagración de la primavera", "Alejo Carpentier", 460.0, "usado", "Granma", "Bayamo"),
    ("Conversación en La Catedral", "Mario Vargas Llosa", 460.0, "usado", "Granma", "Manzanillo"),
    ("La fiesta del Chivo", "Mario Vargas Llosa", 480.0, "nuevo", "Granma", "Manzanillo"),
    ("Trilce", "César Vallejo", 290.0, "usado", "Granma", "Bayamo"),
    ("Boquitas pintadas", "Manuel Puig", 290.0, "usado", "Granma", "Bayamo"),
    ("Como agua para chocolate", "Laura Esquivel", 330.0, "nuevo", "Granma", "Bayamo"),
]

SELLERS = [
    {
        "password": "vendedor123",
        "nombre_tienda": "Librería La Habana",
        "whatsapp_number": "+5355512345",
        "provincia": "La Habana",
        "municipio": "Centro Habana",
        "municipios_envio": ["Plaza de la Revolución", "Habana Vieja", "Cerro", "Playa"],
        "books": [0, 1, 10, 11, 12],
    },
    {
        "password": "vendedor123",
        "nombre_tienda": "Libros del Oriente",
        "whatsapp_number": "+5355598765",
        "provincia": "Santiago de Cuba",
        "municipio": "Santiago de Cuba",
        "municipios_envio": ["Palma Soriano", "Contramaestre", "Songo-La Maya"],
        "books": [2, 3, 4, 13, 14, 15],
    },
    {
        "password": "vendedor123",
        "nombre_tienda": "Tienda Central",
        "whatsapp_number": "+5355567890",
        "provincia": "Villa Clara",
        "municipio": "Santa Clara",
        "municipios_envio": ["Cienfuegos", "Sancti Spíritus", "Placetas", "Caibarién"],
        "books": [5, 6, 7, 8, 9, 16, 17],
    },
    {
        "password": "vendedor123",
        "nombre_tienda": "Librería Vueltabajo",
        "whatsapp_number": "+5354441111",
        "provincia": "Pinar del Río",
        "municipio": "Pinar del Río",
        "municipios_envio": ["Viñales", "San Juan y Martínez", "Consolación del Sur"],
        "books": [18, 19, 20, 21, 22, 23],
    },
    {
        "password": "vendedor123",
        "nombre_tienda": "Atenas Libros",
        "whatsapp_number": "+5354442222",
        "provincia": "Matanzas",
        "municipio": "Matanzas",
        "municipios_envio": ["Cárdenas", "Jovellanos", "Colón", "Jagüey Grande"],
        "books": [24, 25, 26, 27, 28, 29],
    },
    {
        "password": "vendedor123",
        "nombre_tienda": "Librería Agramonte",
        "whatsapp_number": "+5354443333",
        "provincia": "Camagüey",
        "municipio": "Camagüey",
        "municipios_envio": ["Florida", "Nuevitas", "Vertientes", "Esmeralda"],
        "books": [30, 31, 32, 33, 34, 35],
    },
    {
        "password": "vendedor123",
        "nombre_tienda": "Holguín Lecturas",
        "whatsapp_number": "+5354444444",
        "provincia": "Holguín",
        "municipio": "Holguín",
        "municipios_envio": ["Banes", "Mayarí", "Moa", "Gibara"],
        "books": [36, 37, 38, 39, 40, 41],
    },
    {
        "password": "vendedor123",
        "nombre_tienda": "Bayamo Lecturas",
        "whatsapp_number": "+5354445555",
        "provincia": "Granma",
        "municipio": "Bayamo",
        "municipios_envio": ["Manzanillo", "Yara", "Jiguaní", "Guisa"],
        "books": [42, 43, 44, 45, 46, 47, 48, 49],
    },
]

ADMIN = {
    "password": "admin123",
    "nombre_tienda": "Administración LibrosCuba",
    "whatsapp_number": "+5350000000",
    "provincia": "La Habana",
    "municipio": "Plaza de la Revolución",
    "municipios_envio": [],
}


async def _wipe_all(db) -> None:
    """Borra TODO. Solo se usa con --reset."""
    print("[--reset] Borrando TODOS los usuarios y libros...")
    await db.users.delete_many({})
    await db.books.delete_many({})


async def _clear_demo(db) -> None:
    """Elimina solo los registros demo, preservando datos de usuarios reales."""
    demo_ids = [doc["_id"] async for doc in db.users.find({"is_demo": True}, {"_id": 1})]
    if demo_ids:
        await db.books.delete_many({"owner_id": {"$in": demo_ids}})
        await db.users.delete_many({"_id": {"$in": demo_ids}})
        print(f"Datos demo previos eliminados: {len(demo_ids)} usuarios y sus libros.")
    else:
        print("Sin datos demo previos: se insertarán por primera vez.")


async def _upsert_demo_user(db, *, phone: str, base_doc: dict) -> str:
    """
    Inserta o actualiza un usuario demo identificado por su whatsapp_number.
    Devuelve su _id. Conserva la contraseña existente si ya estaba creado
    para no romper sesiones abiertas en el frontend.
    """
    existing = await db.users.find_one({"whatsapp_number": phone})
    if existing:
        update_doc = {k: v for k, v in base_doc.items() if k != "hashed_password"}
        await db.users.update_one({"_id": existing["_id"]}, {"$set": update_doc})
        return existing["_id"]
    user_id = str(uuid4())
    await db.users.insert_one({"_id": user_id, **base_doc})
    return user_id


async def seed(reset: bool) -> None:
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db]

    if reset:
        await _wipe_all(db)
    else:
        await _clear_demo(db)

    now = datetime.now(timezone.utc)

    admin_doc = {
        "hashed_password": hash_password(ADMIN["password"]),
        "whatsapp_number": ADMIN["whatsapp_number"],
        "provincia": ADMIN["provincia"],
        "municipio": ADMIN["municipio"],
        "nombre_tienda": ADMIN["nombre_tienda"],
        "municipios_envio": ADMIN["municipios_envio"],
        "is_admin": True,
        "is_demo": True,
        "created_at": now,
    }
    await _upsert_demo_user(db, phone=ADMIN["whatsapp_number"], base_doc=admin_doc)
    print(f"Admin: {ADMIN['whatsapp_number']} / {ADMIN['password']}")

    seller_books_inserted = 0
    for seller in SELLERS:
        seller_doc = {
            "hashed_password": hash_password(seller["password"]),
            "whatsapp_number": seller["whatsapp_number"],
            "provincia": seller["provincia"],
            "municipio": seller["municipio"],
            "nombre_tienda": seller["nombre_tienda"],
            "municipios_envio": seller.get("municipios_envio", []),
            "is_admin": False,
            "is_demo": True,
            "created_at": now,
        }
        seller_id = await _upsert_demo_user(
            db, phone=seller["whatsapp_number"], base_doc=seller_doc
        )
        print(f"Vendedor: {seller['whatsapp_number']} / {seller['password']}")

        for idx in seller["books"]:
            titulo, autor, precio, estado, provincia, municipio = SEED_BOOKS[idx]
            await db.books.insert_one(
                {
                    "_id": str(uuid4()),
                    "owner_id": seller_id,
                    "titulo": titulo,
                    "autor": autor,
                    "precio": precio,
                    "foto_url": BOOK_IMAGES[idx % len(BOOK_IMAGES)],
                    "descripcion": f"Ejemplar físico en excelente estado. {titulo} disponible en {provincia}.",
                    "estado": estado,
                    "provincia": provincia,
                    "municipio": municipio,
                    "fecha_creacion": now,
                    "cloudinary_public_id": None,
                    "is_demo": True,
                }
            )
            seller_books_inserted += 1

    total_books = await db.books.count_documents({})
    total_users = await db.users.count_documents({})
    real_users = await db.users.count_documents({"is_demo": {"$ne": True}})
    real_books = await db.books.count_documents({"is_demo": {"$ne": True}})
    print(
        f"\nSeed completado: {total_users} usuarios ({real_users} reales preservados), "
        f"{total_books} libros ({real_books} reales preservados). "
        f"Libros demo insertados: {seller_books_inserted}."
    )
    client.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed de LibrosCuba")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Borra TODA la base (usuarios y libros, incluso reales) antes de sembrar.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(seed(reset=args.reset))
