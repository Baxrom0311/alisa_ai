# Kitobxon — Book Reading & Audio Listening Platform

## Goal

Kitob o'qish va audiokitob eshitish uchun mobil ilova backend tizimini ishlab chiqish. Foydalanuvchilar kitoblarni o'qishi, audiolarni tinglashi, progress saqlashi va kutubxonasini boshqarishi mumkin. Backend FastAPI da quriladi, bepul storage xizmatlaridan foydalaniladi.

## Core Features

### 1. Foydalanuvchi tizimi (Auth)
- Ro'yxatdan o'tish (email + parol)
- Login / Logout
- JWT token bilan autentifikatsiya
- Profil ko'rish va tahrirlash

### 2. Kitoblar boshqaruvi
- Kitoblar ro'yxati (CRUD)
- Kitob qo'shish (sarlavha, muallif, tavsif, janr, muqova rasmi, fayl)
- Kitob qidirish va filtrlash (janr, muallif, sarlavha bo'yicha)
- Kitob sahifalarini ko'rish (pagination)
- O'qish progressini saqlash (qaysi sahifada to'xtagan)

### 3. Audiokitoblar
- Audio fayl yuklash va stream qilish
- Audio progressini saqlash (qaysi sekundda to'xtagan)
- Audio metadata (davomiyligi, format, bitrate)

### 4. Kutubxona
- Foydalanuvchi shaxsiy kutubxonasi
- Kitoblarni sevimlilar ro'yxatiga qo'shish
- O'qilgan / o'qilmoqda / o'qilmagan statuslar
- Oxirgi faoliyat tarixi

### 5. Kategoriyalar va teglar
- Kitob janrlari (badiiy, ilmiy, tarixiy, texnik va h.k.)
- Teglar tizimi
- Kategoriya bo'yicha filtrlash

## Tech Stack

- **Backend**: Python 3.11+, FastAPI
- **Database**: SQLite (development), PostgreSQL (production-ready schema)
- **ORM**: SQLAlchemy 2.0 + Alembic (migrations)
- **Auth**: JWT (python-jose + passlib)
- **Storage**: Supabase Storage (bepul tier — 1GB) yoki lokal fayl tizimi (fallback)
- **Audio streaming**: FastAPI StreamingResponse
- **API docs**: Swagger/OpenAPI (FastAPI avtomatik)
- **Testing**: pytest + httpx (async test client)
- **Validation**: Pydantic v2

## Project Structure

```
backend/
  app/
    main.py              # FastAPI app entry point
    config.py            # Settings (env-based)
    database.py          # DB connection & session
    models/              # SQLAlchemy models
      user.py
      book.py
      audio.py
      category.py
      library.py
    schemas/             # Pydantic schemas
      user.py
      book.py
      audio.py
      library.py
    routers/             # API endpoints
      auth.py
      books.py
      audio.py
      library.py
      categories.py
    services/            # Business logic
      auth_service.py
      book_service.py
      audio_service.py
      storage_service.py
    storage/             # Storage backends
      base.py            # Abstract interface
      local.py           # Local filesystem
      supabase.py        # Supabase Storage
    middleware/
      auth.py            # JWT middleware
    utils/
      security.py        # Password hashing, JWT
  alembic/               # DB migrations
  tests/
    conftest.py
    test_auth.py
    test_books.py
    test_audio.py
    test_library.py
  requirements.txt
  .env.example
```

## API Endpoints

### Auth
- `POST /api/auth/register` — Ro'yxatdan o'tish
- `POST /api/auth/login` — Kirish (JWT qaytaradi)
- `GET /api/auth/me` — Joriy foydalanuvchi
- `PUT /api/auth/profile` — Profilni yangilash

### Books
- `GET /api/books` — Kitoblar ro'yxati (pagination, filter, search)
- `GET /api/books/{id}` — Bitta kitob
- `POST /api/books` — Kitob qo'shish (admin)
- `PUT /api/books/{id}` — Kitobni tahrirlash
- `DELETE /api/books/{id}` — Kitobni o'chirish
- `POST /api/books/{id}/cover` — Muqova rasm yuklash
- `POST /api/books/{id}/file` — Kitob faylini yuklash (PDF/EPUB)
- `GET /api/books/{id}/read` — Kitobni o'qish (stream)

### Audio
- `POST /api/books/{id}/audio` — Audio fayl yuklash
- `GET /api/books/{id}/audio/stream` — Audio stream
- `PUT /api/books/{id}/audio/progress` — Audio progressini saqlash
- `GET /api/books/{id}/audio/progress` — Audio progressini olish

### Library
- `GET /api/library` — Mening kutubxonam
- `POST /api/library/{book_id}` — Kutubxonaga qo'shish
- `DELETE /api/library/{book_id}` — Kutubxonadan o'chirish
- `PUT /api/library/{book_id}/status` — Statusni yangilash
- `PUT /api/library/{book_id}/progress` — O'qish progressini saqlash
- `GET /api/library/favorites` — Sevimlilar

### Categories
- `GET /api/categories` — Kategoriyalar ro'yxati
- `POST /api/categories` — Kategoriya qo'shish
- `GET /api/categories/{id}/books` — Kategoriya bo'yicha kitoblar

## Constraints

- Barcha API endpointlar async bo'lishi kerak
- JWT token muddati 24 soat
- Fayl yuklash limiti: 50MB (kitob), 200MB (audio)
- Pagination: default 20, max 100
- Storage: avval lokal, keyin Supabase ga o'tish oson bo'lishi kerak (abstraction layer)
- Parollar bcrypt bilan hash qilinishi kerak
- CORS middleware sozlangan bo'lishi kerak
- Health check endpoint bo'lishi kerak: `GET /api/health`

## Acceptance Criteria

- [ ] `pytest` barcha testlar o'tishi kerak
- [ ] `uvicorn app.main:app` bilan server ishga tushishi kerak
- [ ] `/docs` sahifasida Swagger UI ko'rinishi kerak
- [ ] Foydalanuvchi ro'yxatdan o'tib, login qilib, kitob qo'sha olishi kerak
- [ ] Kitob faylini yuklab, stream qilib o'qiy olishi kerak
- [ ] Audio faylini yuklab, stream qilib eshita olishi kerak
- [ ] Kutubxonaga kitob qo'shib, status va progressini boshqara olishi kerak
- [ ] Storage abstraction layer orqali lokal va Supabase storage ishlay olishi kerak

## Non-Goals

- Frontend / mobil ilova (faqat backend API)
- Real-time xususiyatlar (WebSocket, chat)
- To'lov tizimi
- Admin panel UI
- Email xabarnomalari
- Social login (Google, Facebook)
