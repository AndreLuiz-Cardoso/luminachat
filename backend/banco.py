import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import event
from sqlmodel import Field, Session, SQLModel, create_engine

load_dotenv()  # o main importa este arquivo antes de carregar o .env

ARQUIVO_PADRAO = Path(__file__).parent / "lumina.db"

# sem DATABASE_URL o banco e um arquivo SQLite ao lado do codigo; com ela, pode ser PostgreSQL.
# as hospedagens entregam postgres://, que o SQLAlchemy nao aceita, e o driver instalado e o psycopg
URL = re.sub(
    r"^postgres(ql)?://",
    "postgresql+psycopg://",
    os.getenv("DATABASE_URL") or f"sqlite:///{ARQUIVO_PADRAO.as_posix()}",
)
USA_SQLITE = URL.startswith("sqlite")

engine = create_engine(
    URL,
    pool_pre_ping=True,  # descarta conexoes que o servidor do banco ja derrubou
    connect_args={"check_same_thread": False} if USA_SQLITE else {},
)

if USA_SQLITE:

    @event.listens_for(engine, "connect")
    def configurar_sqlite(conexao, _):
        cursor = conexao.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")  # leituras nao esperam escritas
        cursor.execute("PRAGMA foreign_keys=ON")  # o SQLite ignora chaves estrangeiras por padrao
        cursor.close()


def agora() -> datetime:
    return datetime.now(UTC)


class Usuario(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, max_length=32)
    senha_hash: str
    criado_em: datetime = Field(default_factory=agora)


class Sessao(SQLModel, table=True):
    token_hash: str = Field(primary_key=True)  # guarda o hash: quem ler o banco nao entra como o usuario
    usuario_id: int = Field(foreign_key="usuario.id", index=True, ondelete="CASCADE")
    expira_em: datetime


def criar_tabelas():
    SQLModel.metadata.create_all(engine)


def abrir_banco() -> Iterator[Session]:
    with Session(engine) as banco:
        yield banco
