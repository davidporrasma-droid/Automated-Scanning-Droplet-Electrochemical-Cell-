from sdc.core.grid import Grid
from sdc.calibration.coordinates import Geometry,PlaneAtConstantZ
from sdc.calibration.mesh import fit_plane

def test_grid():
    assert len(Grid().points())==81
    assert Grid(rows=2,columns=2).points()==[(0,0,0.,0.),(0,1,2.,0.),(1,0,0.,2.),(1,1,2.,2.)]
    assert len(Grid(mode='single').points())==1

def test_fit():
    plane=fit_plane([(0,0,1),(1,0,2),(0,1,3),(1,1,4)])
    assert abs(plane.get_z(.5,.5)-2.5)<1e-10

def test_coordinates():
    assert Geometry(100,200,10,5).physical(1,2,PlaneAtConstantZ(12))==(101,202,17,12)
