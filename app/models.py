from typing import Optional, Literal, List, Union
from pydantic import BaseModel, Field


class LinkedInPayload(BaseModel):
    texto: str = Field(
        ...,
        description="Contenido original del post de LinkedIn",
        json_schema_extra={"example": "The IBM Z Student Ambassador Showcase is September 9 at 12PM EDT..."}
    )
    url: str = Field(
        ...,
        description="Enlace del post original",
        json_schema_extra={"example": "https://airtable.com/appnhBCVc9hDgR8mz/paghP08IdSWBkI1Zj/form"}
    )
    empresa: Optional[str] = Field(
        default=None,
        description="Nombre o dominio de la empresa (ej. 'IBM', 'Santander', 'Google', 'Microsoft', 'ibm.com'). Si no se indica, la IA la detectará automáticamente.",
        json_schema_extra={"example": "IBM"}
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
    empresa: Optional[str] = None
    nombre: Optional[str] = None
    asunto: Optional[str] = None
    url: Optional[str] = None
    mensaje: Optional[str] = None
    forum_id: Optional[int] = None
    seccion: int = 0
    publicado: bool = False
