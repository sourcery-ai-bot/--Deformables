import taichi as ti
import math

ti.init(arch=ti.cpu)

# global control
paused = True
damping_toggle = ti.field(ti.i32, ())
curser = ti.Vector.field(2, ti.f32, ())
picking = ti.field(ti.i32,())

# integration method
# 1: explicit euler
# 2: symplectic euler
# 3: implicit euler (you bet)
integration = 2

# procedurally setting up the cantilever
init_x, init_y = 0.1, 0.6
N_x = 20
N_y = 4
# N_x = 2
# N_y = 2
N = N_x*N_y
N_edges = (N_x-1)*N_y + N_x*(N_y - 1) + (N_x-1) * \
    (N_y-1)  # horizontal + vertical + diagonal springs
N_triangles = 2 * (N_x-1) * (N_y-1)
dx = 1/32
curser_radius = dx/2

# physical quantities
m = 1
g = 9.8
YoungsModulus = ti.field(ti.f32, ())

# time-step size (for simulation, 16.7ms)
h = 16.7e-3
# substepping
substepping = 100
# time-step size (for time integration)
dh = h/substepping

# simulation components
x = ti.Vector.field(2, ti.f32, N)
v = ti.Vector.field(2, ti.f32, N)
grad = ti.Vector.field(2, ti.f32, N)
spring_length = ti.field(ti.f32, N_edges)

# geometric components
triangles = ti.Vector.field(3, ti.i32, N_triangles)
edges = ti.Vector.field(2, ti.i32, N_edges)

def ij_2_index(i, j): return i * N_y + j

# -----------------------meshing and init----------------------------
@ti.kernel
def meshing():
    # setting up triangles
    for i,j in ti.ndrange(N_x - 1, N_y - 1):
        # triangle id
        tid = (i * (N_y - 1) + j) * 2
        triangles[tid][0] = ij_2_index(i, j)
        triangles[tid][1] = ij_2_index(i + 1, j)
        triangles[tid][2] = ij_2_index(i, j + 1)

        tid = (i * (N_y - 1) + j) * 2 + 1
        triangles[tid][0] = ij_2_index(i, j + 1)
        triangles[tid][1] = ij_2_index(i + 1, j + 1)
        triangles[tid][2] = ij_2_index(i + 1, j)

    # setting up edges
    # edge id
    eid_base = 0

    # horizontal edges
    for i in range(N_x-1):
        for j in range(N_y):
            eid = eid_base+i*N_y+j
            edges[eid] = [ij_2_index(i, j), ij_2_index(i+1, j)]

    eid_base += (N_x-1)*N_y
    # vertical edges
    for i in range(N_x):
        for j in range(N_y-1):
            eid = eid_base+i*(N_y-1)+j
            edges[eid] = [ij_2_index(i, j), ij_2_index(i, j+1)]

    eid_base += N_x*(N_y-1)
    # diagonal edges
    for i in range(N_x-1):
        for j in range(N_y-1):
            eid = eid_base+i*(N_y-1)+j
            edges[eid] = [ij_2_index(i+1, j), ij_2_index(i, j+1)]


@ti.kernel
def initialize():
    YoungsModulus[None] = 3e4
    paused = True
    # init position and velocity
    for i, j in ti.ndrange(N_x, N_y):
        index = ij_2_index(i, j)
        x[index] = ti.Vector([init_x + i * dx, init_y + j * dx])
        v[index] = ti.Vector([0.0, 0.0])

@ti.kernel
def initialize_springs():
    # init spring rest-length
    for i in range(N_edges):
        a, b = edges[i][0], edges[i][1]
        r = x[a]-x[b]
        spring_length[i] = r.norm()

# ----------------------core-----------------------------
@ti.kernel
def compute_gradient():
    # clear gradient
    for i in grad:
        grad[i] = ti.Vector([0, 0])

    # gradient of elastic potential
    for i in range(N_edges):
        a, b = edges[i][0], edges[i][1]
        r = x[a]-x[b]
        l = r.norm()
        l0 = spring_length[i]
        k = YoungsModulus[None]/l0  # stiffness in Hooke's law
        gradient = k*(l-l0)*r/l
        grad[a] += gradient
        grad[b] += -gradient

@ti.kernel
def update():
    # perform time integration
    for i in range(N):
        if integration == 1:
            # explicit euler integration
            x[i] += dh*v[i]   
            # elastic force + gravitation force, divding mass to get the acceleration
            acc = -grad[i]/m - ti.Vector([0.0, g])
            v[i] += dh*acc
        elif integration == 2:        
            # symplectic integration
            # elastic force + gravitation force, divding mass to get the acceleration
            acc = -grad[i]/m - ti.Vector([0.0, g])
            v[i] += dh*acc
            x[i] += dh*v[i]

    # explicit damping (ether drag)
    for i in v:
        if damping_toggle[None]:
            v[i] *= ti.exp(-dh*5)

    # enforce boundary condition
    for i in range(N):
        if picking[None]:   
            r = x[i]-curser[None]
            if r.norm() < curser_radius:
                x[i] = curser[None]
                v[i] = ti.Vector([0.0, 0.0])
    for j in range(N_y):
        ind = ij_2_index(0, j)
        v[ind] = ti.Vector([0, 0])
        x[ind] = ti.Vector([init_x, init_y + j * dx])  # rest pose attached to the wall

    for i in range(N):
        if x[i][0] < init_x:
            x[i][0] = init_x
            v[i][0] = 0


# init once and for all
meshing()
initialize()
initialize_springs()

gui = ti.GUI('mass-spring system', (800, 800))
while gui.running:

    picking[None]=0

    # key events
    for e in gui.get_events(ti.GUI.PRESS):
        if e.key in [ti.GUI.ESCAPE, ti.GUI.EXIT]:
            exit()
        elif e.key == 'r':
            initialize()
        elif e.key == '0':
            YoungsModulus[None] *= 1.1
        elif e.key == '9':
            YoungsModulus[None] /= 1.1
        elif e.key == ti.GUI.SPACE:
            paused = not paused
        elif e.key in ['d', 'D']:
            damping_toggle[None] = not damping_toggle[None]
        elif e.key in ['p', 'P']:
            for _ in range(substepping):
                compute_gradient()
                update()           

    if gui.is_pressed(ti.GUI.LMB):
        curser[None] = gui.get_cursor_pos()
        picking[None] = 1

    # numerical time integration
    if not paused:
        for _ in range(substepping):
            compute_gradient()
            update()

    # render
    pos = x.to_numpy()
    for i in range(N_edges):
        a, b = edges[i][0], edges[i][1]
        gui.line((pos[a][0], pos[a][1]),
                 (pos[b][0], pos[b][1]),
                 radius=1,
                 color=0xFFFF00)
    gui.line((init_x, 0.0), (init_x, 1.0), color=0xFFFFFF, radius=4)

    if picking[None]:
        gui.circle((curser[None][0], curser[None][1]), radius=curser_radius*800, color=0xFF8888)

    # text
    gui.text(
        content=f'9/0: (-/+) Young\'s Modulus {YoungsModulus[None]:.1f}', pos=(0.6, 0.9), color=0xFFFFFF)
    if damping_toggle[None]:
        gui.text(
            content='D: Damping On', pos=(0.6, 0.875), color=0xFFFFFF)
    else:
        gui.text(
            content='D: Damping Off', pos=(0.6, 0.875), color=0xFFFFFF)
    gui.show()

