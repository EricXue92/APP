from pydantic import BaseModel


class SkillNote(BaseModel):
    name: str
    description: str

    model_config = {"from_attributes": True}


class LevelDetail(BaseModel):
    level: str
    description: str

    model_config = {"from_attributes": True}


class LevelGroup(BaseModel):
    title: str
    levels: list[LevelDetail]
    skills: list[SkillNote]

    model_config = {"from_attributes": True}


class LevelGuideResponse(BaseModel):
    groups: list[LevelGroup]

    model_config = {"from_attributes": True}
