"""Row-major grid, as in the original notebook."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Grid:
    rows:int=9
    columns:int=9
    spacing_x:float=2.0
    spacing_y:float=2.0
    start_x:float=0.0
    start_y:float=0.0
    mode:str='grid'

    def points(self):
        rows,cols=(1,1) if self.mode=='single' else (self.rows,self.columns)
        if self.mode not in ('single','grid') or rows<1 or cols<1: raise ValueError('Invalid grid')
        return [(r,c,self.start_x+c*self.spacing_x,self.start_y+r*self.spacing_y) for r in range(rows) for c in range(cols)]
