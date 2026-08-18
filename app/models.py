from typing import Optional, Literal, List, Union
from pydantic import BaseModel, Field


class LinkedInPayload(BaseModel):
    texto: str = Field(
        ...,
        description="Contenido original del post de LinkedIn",
        json_schema_extra={"example": "Un excelente resumen de cómo implementar RAG con bases de datos vectoriales y embeddings multimodales para mejorar la precisión de los modelos."}
    )
    url: str = Field(
        ...,
        description="Enlace del post original",
        json_schema_extra={"example": "https://www.linkedin.com/posts/ejemplo-rag-123"}
    )
    seccion: Optional[int] = Field(default=0, description="Índice numérico de la sección en Moodle")
    course_id: Optional[Union[int, str, List[Union[int, str]]]] = Field(
        default=None,
        description="ID del curso (ej. 22841, '22842' o dejar nulo para publicar en ambos)",
        json_schema_extra={"example": 22842}
    )


class RecursoItem(BaseModel):
    tipo: Literal["recurso_url", "anuncio_foro"] = "recurso_url"
    course_id: Optional[Union[str, int, List[Union[str, int]]]] = None
    nombre: Optional[str] = None
    asunto: Optional[str] = None
    url: Optional[str] = None
    mensaje: Optional[str] = None
    forum_id: Optional[int] = None
    seccion: int = 0
    publicado: bool = False
