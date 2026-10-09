"""FireScenario data access: a single-row upsert, like the retirement goal."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.fire_scenario import FireScenario


class FireScenarioRepository:
    """FireScenario database operations (single-row upsert)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self) -> FireScenario | None:
        """Get the saved plan, if there is one."""
        return self.db.execute(select(FireScenario)).scalars().first()

    def upsert(self, fields: str, linked: str) -> FireScenario:
        """Create or replace the saved plan.

        Parameters
        ----------
        fields : str
            JSON object of the form's fields.
        linked : str
            JSON list of the fields that follow tracked data.

        Returns
        -------
        FireScenario
            The created or updated record.
        """
        item = self.get()
        if item is None:
            item = FireScenario(fields=fields, linked=linked)
            self.db.add(item)
        else:
            item.fields = fields
            item.linked = linked
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete(self) -> bool:
        """Delete the saved plan; return whether one existed."""
        item = self.get()
        if item is None:
            return False
        self.db.delete(item)
        self.db.commit()
        return True
