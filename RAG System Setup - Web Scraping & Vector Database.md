# Historical note: RAG System Setup / Web Scraping / Vector Database

> Этот документ сохранён как исторический артефакт раннего этапа проекта.
> Он больше не описывает актуальный production-контур полностью.

## Что в нём устарело

В ранней версии проекта здесь обсуждались:
- `infohub.ge` как основной источник;
- ChromaDB как целевое vector storage;
- состояние, в котором scraper ещё не был полноценно прогнан.

Для текущего production это уже неверно.

## Что актуально сейчас

Использовать как source of truth:
1. `docs/CURRENT_STATE.md`
2. `README.md`
3. `docker-compose.yml`

Актуальное состояние сейчас такое:
- upstream: `infohub.rs.ge` + `infohubapi.rs.ge/api`
- vector storage: **PostgreSQL + pgvector**
- public domain: `https://tax-advisor.ge`
- live corpus already populated and indexed

## Зачем файл оставлен

Он может быть полезен как историческая запись о том,
как проект эволюционировал от раннего RAG-черновика к production-системе.
