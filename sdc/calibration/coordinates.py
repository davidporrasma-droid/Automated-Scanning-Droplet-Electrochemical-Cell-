"""Physical grid coordinates and contact geometry."""
from dataclasses import dataclass

@dataclass(frozen=True)
class PlaneAtConstantZ:
    z: float
    def get_z(self, x, y):
        return self.z

@dataclass(frozen=True)
class Geometry:
    ref_x: float
    ref_y: float
    ref_z: float
    clearance: float

    def physical(self, grid_x, grid_y, plane):
        x, y = self.ref_x + grid_x, self.ref_y + grid_y
        contact = plane.get_z(x, y)
        return x, y, contact + self.clearance, contact
