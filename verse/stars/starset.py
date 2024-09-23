import numpy as np
import copy
from scipy.optimize import linprog
import matplotlib.pyplot as plt
import polytope as pc
from z3 import *
from verse.plotter.plotterStar import *
import polytope as pc
from scipy.spatial import ConvexHull
from sklearn.decomposition import PCA
from verse.utils.utils import sample_rect
from typing_extensions import List, Callable

from verse.analysis.dryvr import calc_bloated_tube

import jax
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from scipy.integrate import ode
import pandas as pd

class StarSet:
    """
    StarSet
    a one dimensional star set

    Methods
    -------
    superposition
    from_polytope
    intersection_halfspace
    intersection_poly
    contains_point
    satisfies
    is_empty
    """

    def __init__(
        self,
        center,
        basis,
        #predicate,
        C,
        g
    ):
        """
        

        Parameters
        ----------
        center : np array of numbers
            center of the starset.
        basis : nparray  of nparray of numbers
            basis of the starset
        predicate: boolean function
            function that gives the predicate
        """
        self.n = len(center)
        self.m = len(basis)
        self.center = np.copy(center)
        for vec in basis:
            if len(vec) != self.n:
                raise Exception("Basis for star set must be the same dimension as center")
        self.basis = np.copy(basis)
        if C.shape[1] != self.m:
            raise Exception("Width of C should be equal to " + str(self.m))
        if len(g) !=  len(C):
            raise Exception("Length of g vector should be equal length of C")
        self.C = np.copy(C)
        self.g = np.copy(g)

    def dimension(self):
        return len(self.center)
    def starcopy(self):
        return StarSet(self.center, self.basis, self.C, self.g)

    def superposition(self, new_center, new_basis):
        """
        superposition
        produces a new starset with the new center and basis but same prediate

        Parameters
        ----------
        new_center : number
            center of the starset.
        new_basis : number
            basis of the starset
        """
        if len(new_basis) == len(self.basis):
            return StarSet(new_center, new_basis, self.C, self.g)
        raise Exception("Basis for new star set must be the same")
    

    def calc_reach_tube_linear(self, mode_label,time_horizon,time_step,sim_func,lane_map):
        reach_tubes = []#[[0,self]]
        sim_results = sim_func(mode_label, self.center.copy(), time_horizon, time_step, lane_map)

        new_centers = sim_results[:,1:] #slice off the time
        times = sim_results[:,0] #get the 0th index from all the results
        new_basises = []
        for i in range(0, len(self.basis)):
            vec = self.basis[i]
            new_x = sim_func(mode_label, np.add(self.center, vec), time_horizon, time_step, lane_map)[:,1:]
            new_basises.append([])
            for j in range(0, len(new_x)):
                new_basises[i].append(np.subtract(new_x[j], new_centers[j]))
        for i in range(0, len(new_centers)):
            basis = []
            for basis_list in new_basises:
                basis.append(basis_list[i])
            reach_tubes.append([times[i], self.superposition(new_centers[i], basis)])


        return reach_tubes

    def overapprox_rectangle(self):
        maxes = []
        mins = []
        for i in range(0,self.n):
            min, max = self.get_max_min(i)
            maxes.append(max)
            mins.append(min)

        return [mins, maxes]
            


    def overapprox_rectangles(self):
        # breakpoint()
        # print("this version does work!!")
        #get the sum of each column
        coefficents = self.basis.sum(axis = 0)

        #find the alphas to minimize the pt to fit into the constraints
        res = linprog(c=coefficents, 
                A_ub=self.C, 
                b_ub=self.g, 
                bounds=(None, None))
        min = self.center + (coefficents * res.x)

        #maximize:
        
        invert_coefficents = -1 * coefficents
        res = linprog(c=invert_coefficents, 
                A_ub=self.C, 
                b_ub=self.g, 
                bounds=(None, None))
        max = self.center + (coefficents * res.x)
        return min, max

    def rect_to_star(min_list, max_list):
        if len(min_list) != len(max_list):
            raise Exception("max and min must be same length")
        dims = []
        for i in range(0, len(min_list)):
            dims.append([min_list[i], max_list[i]])
        poly = pc.box2poly(dims)
        return StarSet.from_polytope(poly)

    def calc_reach_tube(self, mode_label,time_horizon,time_step,sim_func,bloating_method,kvalue,sim_trace_num,lane_map,pca):

        if not pca:
            #get rectangle
            initial_set = self.overapprox_rectangle()
            #get reachtube
            bloat_tube = calc_bloated_tube(
                mode_label,
                initial_set,
                time_horizon,
                time_step,
                sim_func,
                bloating_method,
                kvalue,
                sim_trace_num,
                lane_map=lane_map
            )
            #transform back into star
            star_tube = []
            #odd entries: bloat_tube[::2, 1:]   
            #even entries: bloat_tube[1::2, 1:] 
            #data only bloat_tube[ 1:]
            for entry in bloat_tube:
                time = entry[0] 
                data = entry[1:]
                if len(star_tube) > 0:
                    if star_tube[-1][0] == time:
                        star_tube[-1][1] = StarSet.rect_to_star(data,star_tube[-1][1])
                    else:
                        if not isinstance(star_tube[-1][1], StarSet):
                            star_tube[-1][1] = StarSet.rect_to_star(star_tube[-1][1], star_tube[-1][1])
                        star_tube.append([time,data])
                else:
                    star_tube.append([time,data])
            #KB: TODO: where is min for last time point and first time point
            star_tube.pop()
            return star_tube

        else:
            # reach = gen_starsets_post_sim(self, sim_func, time_horizon, time_step, mode_label=mode_label)
            ### theoretically a model should be pre-trained and then loaded here instead of just training and saving no where
            model = get_model(self, sim_func, mode_label, num_epochs=30, T=time_horizon, ts=time_step)
            reach = gen_reachtube(self, sim_func, model, mode_label, T=time_horizon, ts=time_step)
            star_tube = []
            for i in range(len(reach)):
                star_tube.append([i*time_step, reach[i]])

            print('length of reachtube: ', len(star_tube))
            return star_tube


    #def get_new_basis(x_0, new_x_0, new_x_i, basis):


    '''
   prototype function for now. Will likley need more args to properly run simulation
    '''
    def post_cont(self, simulate, t):
        #breakpoint()
        new_center = simulate(self.center,t)
        new_basis = np.empty_like(self.basis)
        for i in range(0, len(self.basis)):
            vec = self.basis[i]
            new_x = simulate(np.add(self.center, vec), t)
            new_basis[i] = np.subtract(new_x, new_center)
        return self.superposition(new_center, new_basis)

    '''
    given a reset function, this will construct a new star set
    '''
    def apply_reset(self, reset_function, expr_list, reset_vars):
        #print("YES WE ARE APPLYING A RESET")
        #center = np.copy(self.center)
        #basis = np.copy(self.basis)
        new_center = reset_function(self.center, expr_list, reset_vars)
        new_basis = np.empty_like(self.basis)
        for i in range(0, len(self.basis)):
            vec = self.basis[i]
            new_x = reset_function(np.add(self.center, vec), expr_list, reset_vars)
            new_basis[i] = np.subtract(new_x, new_center)
        return self.superposition(new_center, new_basis)

    def show(self):
        print(self.center)
        print(self.basis)
        print(self.C)
        print(self.g)
    
    def copy(self):
        star_copy = StarSet(self.center, self.basis, self.C, self.g)
        return star_copy

    def get_halfspace_intersection(starset, constraint_vec, rhs_val):
        #starset.show()
        star_copy = StarSet(starset.center, starset.basis, starset.C, starset.g)
        #star_copy.show()
        star_copy.intersection_halfspace(constraint_vec, rhs_val)
        return star_copy

    '''
    starset intsersection of this star set and a halfspace
    '''
    def intersection_halfspace(self,constraint_vec, rhs_val):
        if not (constraint_vec.ndim == 1) or not (len(constraint_vec == self.n)):
            raise Exception("constraint_vec should be of length n")
        self.intersection_poly(np.array([constraint_vec]), np.array([rhs_val]))

    def intersection_poly(self, constraint_mat, rhs):
        #constraint mat should be length of n and heigh of j and rhs should have length of j
        if not (len(constraint_mat[0] == self.n)):
            raise Exception("constraint_mat vectors should be of length n")
        if not (len(rhs) == len(constraint_mat)):
            raise Exception("constraint_mat should be length of rhs")
        new_c = np.matmul(constraint_mat, self.basis)
        conj_c = np.vstack((self.C, new_c))
        new_g = np.subtract(rhs, np.matmul(constraint_mat, self.center))
        conj_g = np.append(self.g, new_g) 
        self.C = conj_c 
        self.g = conj_g 
#        return None




    def contain_point(self, pt):
        raise Exception("not implemented")
        if not (pt.ndim == 1) and not (len(pt) == self.n):
            raise Exception("pt should be n dimensional vector")
        #affine transformation of point with baisis as generator and cneter as offset
        #then check if 
        #print(self.basis)
        intermediate = np.matmul(np.transpose(self.basis), pt) 
        #print(intermediate)
        p_prime = np.add(intermediate,self.center)
        #print("this is alpha!!!")
        #print(p_prime)
        print(p_prime)
        print(self.C)
        return False #self.predicate(p_prime)
    def from_polytope(polytope):
        return StarSet.from_poly(polytope.A, polytope.b)


    def from_poly(constraint_mat, rhs):
        if not (len(rhs) == len(constraint_mat)):
            raise Exception("constraint_mat should be length of rhs")
        n = len(constraint_mat[0])
        center = np.zeros(n)
        basis = np.zeros((n, n))
        for index in range(0,n):
            basis[index][index] = 1.0
        return StarSet(center,basis, constraint_mat, rhs)

    def to_poly(self):
        raise Exception("to_poly not implemented")
        #new_constraint_mat =np.matmul(self.C,np.linalg.inv(self.basis)) - self.center
        #new_rhs = self.g
        new_constraint_mat =np.matmul(self.C,self.basis) + self.center
        new_rhs = self.g

        return (new_constraint_mat, new_rhs)

    '''
   returns true if entire star set is contained within the half_space A*x <= b
    '''
    def satisfies(self,constraint_vec, rhs):
        #check if the intersection Ax > b is emtpy. We can only check <= in scipy
        #TODO: improve to find check -Ax < -b instead of -Ax <= -b
        new_star = StarSet.get_halfspace_intersection(self, -1 * constraint_vec,-1*rhs)
        #new_star.show()
        #if new star is empty, this star is entirely contained in input halfspace
        return new_star.is_empty()

    def contains_point(self, point):
        print("in solver")
        cur_solver = Solver() 
        #create alpha vars
        alpha = [ Real("alpha_%s" % (j+1)) for j in range(len(self.basis)) ]
        #create state vars
        #state_vec = [ Real("state_%s" % (j+1)) for j in range(len(self.center)) ] 
        #add the equality constraint
        #x = x_0 + sum of alpha*
        for j in range(len(point)):
            new_eq = self.center[j]
            for i in range(len(self.basis)):
                #take the sum of alpha_i times the jth index of each basis
                new_eq = new_eq + (alpha[i]*self.basis[i][j])
            cur_solver.add(new_eq == point[j])

        #add the constraint on alpha
        for i in range(len(self.C)):
            new_eq = 0
            for j in range(len(alpha)):
                new_eq = new_eq + (self.C[i][j] * alpha[j])
            cur_solver.add(new_eq <= self.g[i])
           
       
        if cur_solver.check() == sat:
            return True
        return False
        #print(cur_solver.model())

    
    def add_constraints(self, cur_solver, state_vec, agent):
        #print("checking guards")
        #breakpoint()
        #state vec contains the list of z3 variables for the state in the order of the state vectors for the star set
        #rest is same as above but change point to state vec
        #create alpha vars
        alpha = [ Real("%s_alpha_%s" % (agent, (j+1))) for j in range(len(self.basis)) ]
        #create state vars
        #state_vec = [ Real("state_%s" % (j+1)) for j in range(len(self.center)) ] 
        #add the equality constraint
        #x = x_0 + sum of alpha*
        mat = self.center + (self.basis.transpose() @ alpha)
        for i in range(0, len(mat)):
            cur_solver.add(mat[i] == state_vec[i])
        #for j in range(len(state_vec)):
        #    new_eq = self.center[j]
        #    for i in range(len(self.basis)):
        #        #take the sum of alpha_i times the jth index of each basis
        #        new_eq = new_eq + (alpha[i]*self.basis[i][j])
        #    cur_solver.add(new_eq == state_vec[j])

        #add the constraint on alpha
        for i in range(len(self.C)):
            new_eq = 0
            for j in range(len(alpha)):
                new_eq = new_eq + (self.C[i][j] * alpha[j])
            cur_solver.add(new_eq <= self.g[i])
        #print(cur_solver)
        #return cur_solver
    
    def union():
        #TODO: likely need
        return None

    def intersect(star1, star2):
        return None

    def plot(self):
        xs, ys = StarSet.get_verts(self)
        #print(verts)
        plt.plot(xs, ys)
        plt.show()

    def get_center_pt(self, x_dim, y_dim):
        return (self.center[x_dim], self.center[y_dim])

    #stanley bak code
    def get_verts(stateset, dim1=None, dim2=None):
        """get the vertices of the stateset"""
        #TODO: generalize for n dimensional
        verts = []
        x_pts = []
        y_pts = []
        extra_dims_ct = len(stateset.center) - 2
        zeros = []
        for i in range(0, extra_dims_ct):
            zeros.append([0])
        # sample the angles from 0 to 2pi, 100 samples
        # for angle in np.linspace(0, 2*np.pi, 100):
        for angle in np.linspace(0, 2*np.pi, 100):
            x_component = np.cos(angle)
            y_component = np.sin(angle)
            #TODO: needs to work for 3d and any dim of non-graphed state
            if dim1 is None or dim2 is None:
                direction = [[x_component], [y_component]]
                direction.extend(zeros)
            else:
                direction = [[0] for _ in range(stateset.dimension())]
                direction[dim1] = [x_component]
                direction[dim2] = [y_component] 
            direction = np.array(direction)
            #for i in range(0, extra_dims_ct):
            #    direction.append([0])
            #direction.extend(zeros)

            pt = stateset.maximize(direction)

            # verts.append(pt)
            verts.append([pt[0][dim1], pt[0][dim2]])
            #print(pt)
            if dim1 is None or dim2 is None:
                x_pts.append(pt[0][0])
                #print(pt[0][0])
                y_pts.append(pt[0][1])
            else:
                x_pts.append(pt[0][dim1])
                y_pts.append(pt[0][dim2])
            #print(pt[1][0])
        verts = np.array(verts)
        ### these three lines whether to use convex hull or not
        # ch = ConvexHull(verts)
        # verts = np.vstack((verts[ch.vertices], verts[ch.vertices[0]]))
        # return (verts[:, 0], verts[:, 1])
        x_pts.append(x_pts[0])
        y_pts.append(y_pts[0])
        return (x_pts, y_pts)

#stanley bak code
    def maximize(self, opt_direction):
        """return the point that maximizes the direction"""

        opt_direction *= -1

        # convert opt_direction to domain
        #print(self.basis)
        domain_direction = opt_direction.T @ self.basis


        # use LP to optimize the constraints
        res = linprog(c=domain_direction, 
                A_ub=self.C, 
                b_ub=self.g, 
                bounds=(None, None))
        
        # convert point back to range
        #print(res.x)
        domain_pt = res.x.reshape((res.x.shape[0], 1))
        #if domain_direction[0][0] == -1 and domain_direction[0][1] == 0:
        #    print(domain_pt)
        #range_pt = self.center + self.basis @ domain_pt
        range_pt = self.center + domain_pt.T @ self.basis # does this makes sense for the alpha of the basis vectors not included

        #if domain_direction[0][0] == -1 and domain_direction[0][1] == 0:
        #    print(self.basis)
        #    print(range_pt)
        # return the point
        return range_pt
    
    def get_true_center(self):
        #maxes = []
        #mins = []
        pt = []
        for i in range(0,self.n):
            min, max = self.get_max_min(i)
            pt.append(max - min / 2)
            #maxes.append(max)
            #mins.append(min)
        return pt


    def get_max_min(self, i):
        #breakpoint()
        #take the ith index of each basis
        coefficents = self.basis[:,i]

        #minimize ith pt to fit into the constraints
        res = linprog(c=coefficents, 
                A_ub=self.C, 
                b_ub=self.g, 
                bounds=(None, None))
        min = self.center[i] + (coefficents @ res.x)

        #maximize:
        invert_coefficents = -1 * coefficents
        res = linprog(c=invert_coefficents, 
                A_ub=self.C, 
                b_ub=self.g, 
                bounds=(None, None))
        max = self.center[i] + (coefficents @ res.x)
        return min, max


#    '''
#   returns true if star set intersects the half space
#    '''
#    def intersects():
#        return None

    def is_empty(self):
        feasible = StarSet.is_feasible(self.n,self.C,self.g)
        if feasible:
            return False
        return True

    def is_feasible(n, constraint_mat, rhs, equal_mat=None, equal_rhs=None):
        results = linprog(c=np.zeros(n),A_ub=constraint_mat,b_ub=rhs,A_eq=equal_mat, b_eq=equal_rhs)
        if results.status == 0:
            return True
        if results.status == 2:
            return False
        raise Exception("linear program had unexpected result")

    def combine_stars(stars):
        new_rect = []
        for i in range(0, stars[0].n):
            max = None
            min = None
            for star in stars:
                this_min, this_max = star.get_max_min(i)
                if min == None or this_min < min:
                    min = this_min
                if max == None or this_max > max:
                    max = this_max
            new_rect.append([min, max])
        import polytope as pc
        return StarSet.from_polytope(pc.box2poly(new_rect))

    def print(self) -> None:
        print(f'{self.center}\n------\n{self.basis}\n------\n{self.C}\n------\n{self.g}')

class HalfSpace:
    '''
    Parameters
    --------------------
    H : vector in R^n
    g : value in R 
    '''
    def __init__(self, H, g):
        self.H = H
        self.g = g

### from star_util

def containment_poly(star: StarSet, point: np.ndarray) -> bool:
    if star.dimension() != point.shape[0]:
        raise ValueError(f'Dimension of point does not match the dimenions of the starset')
    
    center, basis, C, g = star.center, star.basis, star.C, star.g
    # print(basis, basis.shape, C, C.shape)
    alpha = RealVector('a', C.shape[1]) # holds list of alphas, should we be taking length from C or basis?
    s = Solver()

    ### add equality constraints
    for i in range(star.dimension()):
        exp = center[i]
        for j in range(len(alpha)):
            exp += alpha[j]*basis[j][i] # from the jth alpha/v, grab the ith dimension
        # print(exp)
        s.add(exp == point[i])

    ### add alpha constraints
    for i in range(C.shape[0]): # iterate over each row
        exp = 0 # there's probably a better way to do this, but this works
        for j in range(len(alpha)): # iterate over alphas
            exp += C[i][j]*alpha[j]
        # print(exp)
        s.add(exp <= g[i])

    return s.check()==sat

### N is the number of points, tol is how many misses consecutively we can see before raising an error  
def sample_star(star: StarSet, N: int, tol: float = 0.2) -> List[List[float]]:
    
    star = StarSet(np.round(star.center, 6), np.round(star.basis, 6), np.round(star.C, 6), np.round(star.g, 6))
 
    rect = star.overapprox_rectangle()
    points = []
    misses = 0
    while len(points)<N:
        point = np.array(sample_rect(rect))
        if containment_poly(star, point):
            points.append(point)
            misses = 0
        else:
            misses+=1
            if misses>int(N*tol):
                star.print()
                print(rect)
                containment_poly(star, point)
                raise Exception("Too many consecutive misses, halting function. Call smple_rect instead.")
    return points

# def post_cont_pca(old_star: StarSet, new_center: np.ndarray, derived_basis: np.ndarray,  points: np.ndarray) -> StarSet:
def post_cont_pca(old_star: StarSet, derived_basis: np.ndarray,  points: np.ndarray, usat: Bool = False) -> StarSet:
    if points.size==0:
        raise ValueError(f'No points given as input')
    if old_star.dimension() != points.shape[1]:
        raise ValueError(f'Dimension of points does not match the dimenions of the starset')
    if  old_star.basis.shape != derived_basis.shape:
        raise ValueError(f'Dimension of given basis does not match basis of original starset')

    ### these two lines exist to resolve some precision issues, things like 0.2 and 0 aren't actually 0.2 and 0 but rather 0.200000004 and 9e-63 which causes errors when using the solver
    center, basis, C, g = old_star.center, old_star.basis, old_star.C, old_star.g
    # derived_basis = np.around(derived_basis, decimals=10) 
    # points = np.around(points, decimals=10)
    new_center = np.around(np.average(points, axis=0), decimals=15)
    alpha = [RealVector(f'a_{i}', C.shape[1]) for i in range(points.shape[0])]
    u = Real('u')
    c = RealVector('i', old_star.dimension())

    o = Optimize()
    ### add equality constraints
    for p in range(len(points)):
        point = points[p]
        for i in range(old_star.dimension()):
            # exp = new_center[i]
            exp = c[i]
            for j in range(len(alpha[p])):
                exp += alpha[p][j]*derived_basis[j][i] # from the jth alpha/v, grab the ith dimension
            # print(exp)
            o.add(exp == point[i])

        ### add alpha constraints
        for i in range(C.shape[0]): # iterate over each row
            exp = 0 # there's probably a better way to do this, but this works
            for j in range(len(alpha[p])): # iterate over alphas
                exp += C[i][j]*alpha[p][j]
            o.add(exp <= u*g[i])
    
    o.minimize(u)

    model = None
    new_basis = derived_basis

    if o.check() == sat: 
        model = o.model()
    else:
        ### think about doing post_cont_pca except with an always valid predicate, i.e., [1, 0, ...0, , -1], [1, ..., 1] -- may be able to do this with just box2poly
        if not usat: ### see if this works, could also move this in gen_starset if efficiency is more of a concern than possible compactness
            # print("Solution not found with current predicate, trying a generic predicate instead.")
            return post_cont_pca(new_pred(old_star), derived_basis, points, True)
        raise RuntimeError(f'Optimizer was unable to find a valid mu') # this is also hit if the function is interrupted

    print(model[u].as_decimal(10))
    new_center = np.array([float(model[c[i]].as_fraction()) for i in range(len(c))])
    return StarSet(new_center, np.array(derived_basis), C, g * float(model[u].as_fraction()))

# alternatively this could just take the dimension of the starset
def new_pred(old_star: StarSet) -> StarSet:
    cols = old_star.C.shape[1] # should be == old_star.dimension
    new_C = []
    ### this loop generates a zonotope predicate, i.e., each alpha gets [-1, 1] range 
    for i in range(cols): ### there' probably a faster way to do this, possibly using a lambda function
        col_i = []
        for j in range(cols*2):
            if i*2==j:
                col_i.append(1)
            elif i*2+1==j:
                col_i.append(-1)
            else:
                col_i.append(0)
        new_C.append(col_i)
    new_C = np.transpose(np.array(new_C))
    new_g = np.ones(old_star.g.shape)
    return StarSet(old_star.center, old_star.basis, new_C, new_g)

### from a set of points at a given time, generate a starset -- could possible reformat or remake this function to be more general
### expects an input with shape N (num points) x n (state dimenion) NOT N x n+1 (state dimension + time)
### this may get an exception if mu can't be generated, either figure out what to do about that or modify post_cont_pca s.t. it doesn't throw an error
def gen_starset(points: np.ndarray, old_star: StarSet) -> StarSet:
    new_center = np.mean(points, axis=0) # probably won't be used, delete if unused in final product
    pca: PCA = PCA(n_components=points.shape[1])
    pca.fit(points)
    scale = np.sqrt(pca.explained_variance_)
    # print(pca.components_.T, '...', scale, '\n_____\n', )
    derived_basis = (pca.components_.T @ np.diag(scale)).T # scaling each component by sqrt of dimension
    # print(derived_basis, '\n_____\n')
    return post_cont_pca(old_star, derived_basis, points)

def starset_loss(C: np.ndarray, g: np.ndarray, derived_basis: np.ndarray, points: np.ndarray, mu: float) -> float:
    output = mu
    x_0 = np.mean(points, axis=0) # this should be a parameter to optimze in the future but hold it here for now
    V_m1 = np.linalg.inv(derived_basis.T) # derived_basis assumed to be invertible, may not necessarily be true right now
    for point in points:
        contain = C@V_m1@(point-x_0)-mu*g ### kxm mxm nx1 - kx1 = kx1, should work so long as m=n which is the case if doing by PCA
        output += jax.numpy.linalg.norm(jax.nn.relu(contain), ord=np.inf) ### unsure if l inf norm or any norm is the correct approach
    return output

def gen_starset_grad(points: np.ndarray, old_star: StarSet) -> StarSet:
    new_center = np.mean(points, axis=0) # probably won't be used, delete if unused in final product
    pca: PCA = PCA(n_components=points.shape[1])
    pca.fit(points)
    scale = np.sqrt(pca.explained_variance_)
    derived_basis = (pca.components_.T @ np.diag(scale)).T # scaling each component by sqrt of dimension
    
    grad = jax.grad(starset_loss, argnums=4) # following Yangge's example
    mu = 1.0
    lr = 0.01 # assuming this is a hyperparameter for adjustment rate
    for i in range(100):
        grads = grad(old_star.C, old_star.g, derived_basis, points, mu)
        mu = mu - lr*grads ### does this work? apparently I should change grad to specify an argnum=3, but unsure if this is correct
    print(mu)
    return StarSet(new_center, derived_basis, old_star.C, mu*old_star.g)

### doing post_computations using simulation then constructing star sets around each set of points afterwards -- not iterative
### modified N from 100 to 30 for helicopter scenario
def gen_starsets_post_sim(old_star: StarSet, sim: Callable, T: float = 7, ts: float = 0.05, N: int = 30, no_init: bool = False, mode_label: int = None) -> List[StarSet]:
    points = np.array(sample_star(old_star, N))
    post_points = []
    if no_init: 
        for point in points:
            post_points.append(sim(mode=mode_label, initialCondition=point, time_bound=T, time_step=ts).tolist()[1:])
    else:
        for point in points:
            # post_points.append(sim(mode=mode_label, initialCondition=point, time_bound=T, time_step=ts).tolist())
            post_points.append(sim(mode_label, point, T, ts).tolist())
    post_points = np.array(post_points)
    stars: List[StarSet] = []
    for t in range(post_points.shape[1]): # pp has shape N x (T/dt) x (n + 1), so index using first 
        stars.append(gen_starset(post_points[:, t, 1:], old_star)) 
        # stars.append(gen_starset_grad(post_points[:, t, 1:], old_star)) ### testing out new algorithm here, could also do so in startests if I remember 
    for t in range(post_points.shape[1]):
        plt.scatter(post_points[:, t, 1], post_points[:, t, 2])
    return stars

### doing sim and post_cont iteratively to construct new starsets and get new points from them every ts
### this takes a decent amount of time -- guessing coming from post_cont_pca and/or sample_star as sim should be pretty fast
### sample star may be taking a while
### also size of star set blows up quickly, check what's going on -- probably need a better/different plotter function now
def sim_star(init_star: StarSet, sim: Callable, T: int = 7, ts: float = 0.05, N: int = 100) -> List[StarSet]:
    t = 0
    stars: List[StarSet] = []
    old_star = init_star
    while t<T:
        new_star = gen_starsets_post_sim(old_star, sim, ts, ts, N, True)[0] # gen_starset should return a list including only one starset
        stars.append(new_star)
        t += ts
        old_star = copy.deepcopy(new_star)
    return stars

'''
Utility function to see if there's anything wrong with the post_cont_pca alg
'''
def check_unsat(old_star: StarSet, derived_basis: np.ndarray, point: np.ndarray, ncenter: np.ndarray = None) -> bool:
    center, basis, C, g = old_star.center, old_star.basis, old_star.C, old_star.g        
    alpha = RealVector('a', C.shape[1])
    u = Real('u')
    c = RealVector('i', old_star.dimension())
    new_center = ncenter
    o = Optimize()

    for i in range(old_star.dimension()):
        exp = new_center[i]
        # exp = c[i]
        for j in range(len(alpha)):
            exp += alpha[j]*derived_basis[j][i] # from the jth alpha/v, grab the ith dimension
        # print(exp)
        o.add(exp == point[i])

    ### add alpha constraints
    for i in range(C.shape[0]): # iterate over each row
        exp = 0 # there's probably a better way to do this, but this works
        for j in range(len(alpha)): # iterate over alphas
            exp += C[i][j]*alpha[j]
        o.add(exp <= u*g[i])
    
    # o.minimize(u)

    if o.check() == unsat:
        print(o.sexpr())
    return o.check() == unsat

'''
Visualization functions
'''

def plot_stars_points(stars: List[StarSet], points: np.ndarray = None):
    for star in stars:
        x, y = np.array(star.get_verts())
        plt.plot(x, y, lw = 1)
        centerx, centery = star.get_center_pt(0, 1)
        plt.plot(centerx, centery, 'o')
    if points is not None:
        plt.scatter(points[:, 0], points[:, 1])
    # plt.show()

def gen_starsets_post_sim_vis(old_star: StarSet, sim: Callable, T: float = 7, ts: float = 0.05, N: int = 100, no_init: bool = False) -> List[StarSet]:
    points = np.array(sample_star(old_star, N, tol=10)) ### sho
    post_points = []
    if no_init: 
        for point in points:
            post_points.append(sim(mode=None, initialCondition=point, time_bound=T, time_step=ts).tolist()[1:])
    else:
        for point in points:
            post_points.append(sim(mode=None, initialCondition=point, time_bound=T, time_step=ts).tolist())
    post_points = np.array(post_points)
    stars: List[StarSet] = []
    for t in range(post_points.shape[1]): # pp has shape N x (T/dt) x (n + 1), so index using first 
        stars.append(gen_starset(post_points[:, t, 1:], old_star))
    # print(post_points)
    plot_stars_points(stars, post_points[:, 0, 1:]) # this only makes sense if points is 2D, i.e., only simulated one ts
    return stars

def plot_stars_points_nonit(stars: List[StarSet], points: np.ndarray):
    for star in stars:
        x, y = np.array(star.get_verts())
        plt.plot(x, y, lw = 1)
        centerx, centery = star.get_center_pt(0, 1)
        plt.plot(centerx, centery, 'o')
    for t in range(points.shape[1]): # pp has shape N x (T/dt) x (n + 1), so index using first 
        plt.scatter(points[:, t, 1], points[:, t, 2])
    # plt.show()

def gen_starsets_post_sim_vis_nonit(old_star: StarSet, sim: Callable, T: float = 7, ts: float = 0.05, N: int = 100, no_init: bool = False) -> None:
    points = np.array(sample_star(old_star, N, tol=10)) ### sho
    post_points = []
    if no_init: 
        for point in points:
            post_points.append(sim(mode=None, initialCondition=point, time_bound=T, time_step=ts).tolist()[1:])
    else:
        for point in points:
            post_points.append(sim(mode=None, initialCondition=point, time_bound=T, time_step=ts).tolist())
    post_points = np.array(post_points)
    stars: List[StarSet] = []
    for t in range(post_points.shape[1]): # pp has shape N x (T/dt) x (n + 1), so index using first 
        stars.append(gen_starset(post_points[:, t, 1:], old_star))
        # print(np.inner(*stars[-1].basis), '\n ----------- \n', *stars[-1].basis)
    # print(post_points)
    plot_stars_points_nonit(stars, post_points) # this only makes sense if points is 2D, i.e., only simulated one ts
    plt.show()

def plot_stars_points_nonit_nd(stars: List[StarSet], points: np.ndarray, dim1, dim2):
    for star in stars:
        x, y = np.array(star.get_verts(dim1, dim2))
        plt.plot(x, y, lw = 1)
        # plt.plot(x, y, 'b', lw = 1)
        centerx, centery = star.get_center_pt(dim1, dim2)
        plt.plot(centerx, centery, 'o')
    for t in range(points.shape[1]): # pp has shape N x (T/dt) x (n + 1), so index using first 
        plt.scatter(points[:, t, dim1+1], points[:, t, dim2+1])
    # plt.show()

def gen_starsets_post_sim_vis_nonit_nd(old_star: StarSet, sim: Callable, T: float = 7, ts: float = 0.05, N: int = 100, no_init: bool = False, dim1=0, dim2=1) -> None:
    points = np.array(sample_star(old_star, N, tol=10)) ### sho
    post_points = []
    if no_init: 
        for point in points:
            post_points.append(sim(mode=None, initialCondition=point, time_bound=T, time_step=ts).tolist()[1:])
    else:
        for point in points:
            post_points.append(sim(mode=None, initialCondition=point, time_bound=T, time_step=ts).tolist())
    post_points = np.array(post_points)
    stars: List[StarSet] = []
    for t in range(post_points.shape[1]): # pp has shape N x (T/dt) x (n + 1), so index using first 
        stars.append(gen_starset(post_points[:, t, 1:], old_star))
        # print(np.inner(*stars[-1].basis), '\n ----------- \n', *stars[-1].basis)
    # print(post_points)
    if dim1>=old_star.dimension():
        dim1 = 0
    if dim2>old_star.dimension():
        dim2 = 1
    plot_stars_points_nonit_nd(stars, post_points, dim1, dim2) # this only makes sense if points is 2D, i.e., only simulated one ts
    plt.show()

def sim_star_vis(init_star: StarSet, sim: Callable, T: int = 7, ts: float = 0.05, N: int = 100) -> None:
    t = 0
    stars: List[StarSet] = []
    old_star = init_star
    while t<T:
        new_star = gen_starsets_post_sim_vis(old_star, sim, ts, ts, N, True)[0] # gen_starset should return a list including only one starset
        stars.append(new_star)
        ### print out each star set, check for orthogonality
        t += ts
        old_star = copy.deepcopy(new_star)
    plt.show()
    # return stars

### need to refactor this file so all the starset operations are separate from the definitions

class PostNN(nn.Module):
    def __init__(self, input_size, hidden_size, output_size):
        super(PostNN, self).__init__()
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.fc2 = nn.Linear(hidden_size, hidden_size)
        self.fc4 = nn.Linear(hidden_size, hidden_size)
        self.fc3 = nn.Linear(hidden_size, output_size)
        # self.relu = nn.ReLU()
        self.relu = nn.LeakyReLU()
        self.tanh = nn.Tanh()

    def forward(self, x):
        x = self.fc1(x)
        x = self.relu(x)
        # x = self.tanh(x)
        x = self.fc2(x)
        x = self.relu(x)
        x = self.fc4(x)
        x = self.relu(x)
        # x = self.tanh(x)
        x = self.fc3(x)
        x = self.relu(x)

        return x

C = np.transpose(np.array([[1,-1,0,0],[0,0,1,-1]]))
g = np.array([1,1,1,1])
basis = np.array([[1, 0], [0, 1]]) * np.diag([.1, .1])
center = np.array([1.40,2.30])

def create_model(input_size: int = 1, hidden_size: int = 64, output_size: int =1) -> PostNN:
    return PostNN(input_size, hidden_size, output_size)

def he_init(m):
    if isinstance(m, nn.Linear):
        nn.init.kaiming_normal_(m.weight, nonlinearity='relu')  # Apply He Normal Initialization
        if m.bias is not None:
            nn.init.constant_(m.bias, 0)  # Initialize biases to 0 (optional)

def model_he_init(model: PostNN) -> None: 
    def he_init(m) -> None: 
        if isinstance(m, nn.Linear):
            nn.init.kaiming_normal_(m.weight, nonlinearity='relu')  # Apply He Normal Initialization
            if m.bias is not None:
                nn.init.constant_(m.bias, 0)  # Initialize biases to 0 (optional)
    
    model.apply(he_init)
    
def train(initial: StarSet, sim: Callable, model: PostNN, mode_label: int = None, num_epochs: int = 50, num_samples: int = 100, T: float = 7, ts: float=0.1, lamb: float = 7) -> None:
    # Use SGD as the optimizer
    optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-5)
    scheduler = optim.lr_scheduler.ExponentialLR(optimizer, gamma=0.95)

    times = torch.arange(0, T+ts, ts) # times to supply, right now this is fixed while S_t is random. can consider making this random as well

    C = torch.tensor(initial.C, dtype=torch.double)
    g = torch.tensor(initial.g, dtype=torch.float)
    # Training loop
    S_0 = sample_star(initial, num_samples*10) # should eventually be a hyperparameter as the second input, 
    np.random.seed()

    def sample_initial(num_samples: int = num_samples) -> List[List[float]]:
        samples = []
        for _ in range(num_samples):
            samples.append(S_0[np.random.randint(0, len(S_0))])
        return samples

    for epoch in range(num_epochs):
        # Zero the parameter gradients
        optimizer.zero_grad()

        samples = sample_initial()

        post_points = []
        for point in samples:
                post_points.append(sim(mode_label, point, T, ts).tolist())
        post_points = np.array(post_points) ### this has shape N x (T/ts) x (n+1), S_t is equivalent to p_p[:, t, 1:]
        
        bases = [] # now grab V_t 
        centers = [] ### eventually this should be a NN output too
        for i in range(len(times)):
            points = post_points[:, i, 1:]
            new_center = np.mean(points, axis=0) # probably won't be used, delete if unused in final product
            pca: PCA = PCA(n_components=points.shape[1])
            pca.fit(points)
            scale = np.sqrt(pca.explained_variance_)
            derived_basis = (pca.components_.T @ np.diag(scale)) # scaling each component by sqrt of dimension
            bases.append(torch.tensor(derived_basis))
            centers.append(torch.tensor(new_center))

        n = int(len(bases[0]) ** 0.5) 
        
        post_points = torch.tensor(post_points)
        for i in range(len(times)):
            # Forward pass
            t = torch.tensor([times[i]], dtype=torch.float32)
            mu = model(t)
            n = initial.dimension()
            # Compute the loss
            # cont = lambda p, i: torch.linalg.vector_norm(torch.relu(C@torch.linalg.inv(bases[i])@(p-centers[i])-mu*g))
            cont = lambda p, i: torch.linalg.vector_norm(torch.relu(C@torch.linalg.inv(bases[i]+1e-6*torch.eye(n))@(p-centers[i])-mu*g))
            loss = torch.log1p(mu) + lamb*torch.sum(torch.stack([cont(point, i) for point in post_points[:, i, 1:]]))/num_samples 

            loss.backward()
            optimizer.step()
            
        scheduler.step()

        # # Print loss periodically
        # # print(f'Loss: {loss.item():.4f}')
        if (epoch + 1) % 10 == 0:
            print(f'Epoch [{epoch + 1}/{num_epochs}] \n_____________\n')
        #     # print("Gradients of weights and loss", model.fc1.weight.grad, model.fc1.bias.grad)
        #     for i in range(len(times)):
        #         t = torch.tensor([times[i]], dtype=torch.float32)
        #         mu = model(t)
        #         cont = lambda p, i: torch.linalg.vector_norm(torch.relu(C@torch.linalg.inv(bases[i])@(p-centers[i])-mu*g))
        #         loss = torch.log1p(mu)  + lamb*torch.sum(torch.stack([cont(point, i) for point in post_points[:, i, 1:]]))/len(post_points[:,i,1:])
        #         # loss = (1-lamb)*mu + lamb*torch.sum(torch.stack([cont(point, i) for point in post_points[:, i, 1:]]))/len(post_points[:,i,1:])
        #         print(f'loss: {loss.item():.4f}, mu: {mu.item():.4f}, time: {t.item():.1f}')

def get_model(initial: StarSet, sim: Callable, mode_label: int = None, num_epochs: int = 50, num_samples: int = 100, T: float = 7, ts: float=0.1, lamb: float = 7, input_size: int = 1, hidden_size: int = 64, output_size: int = 1) -> PostNN:
    model = create_model(input_size, hidden_size, output_size)
    model_he_init(model)
    train(initial, sim, model, mode_label, num_epochs, num_samples, T, ts, lamb)
    model.eval()
    return model

def gen_reachtube(initial: StarSet, sim: Callable, model: PostNN, mode_label: int = None, num_samples: int=1000, T: float = 7, ts: float = 0.1) -> List[StarSet]:
    S = sample_star(initial, num_samples)
    post_points = []
    for point in S:
            post_points.append(sim(mode_label, point, T, ts).tolist())
    post_points = np.array(post_points) ### this has shape N x (T/ts) x (n+1), S_t is equivalent to p_p[:, t, 1:]

    test_times = torch.arange(0, T+ts, ts)
    test = torch.reshape(test_times, (len(test_times), 1))
    bases = [] # now grab V_t 
    centers = [] ### eventually this should be a NN output too
    for i in range(len(test_times)):
        points = post_points[:, i, 1:]
        new_center = np.mean(points, axis=0) # probably won't be used, delete if unused in final product
        pca: PCA = PCA(n_components=points.shape[1])
        pca.fit(points)
        scale = np.sqrt(pca.explained_variance_)
        # print(pca.components_, scale)
        derived_basis = (pca.components_.T @ np.diag(scale)).T # scaling each component by sqrt of dimension
        # derived_basis = (pca.components_.T ).T # scaling each component by sqrt of dimension
        # print(pca.components_[0]*scale[0], pca.components_[1]*scale[1])
        # plt.arrow(new_center[0], new_center[1], *derived_basis[0]
        bases.append(torch.tensor(derived_basis))
        # bases.append(torch.eye(points.shape[1], dtype=torch.double))
        centers.append(torch.tensor(new_center))
    
    C = torch.tensor(initial.C, dtype=torch.double)
    g = torch.tensor(initial.g, dtype=torch.float)

    stars = []
    cont = lambda p, i: torch.linalg.vector_norm(torch.relu(C@torch.linalg.inv(bases[i].T)@(p-centers[i])-model(test[i])*g))
    for i in range(len(test_times)):
        # mu, center = model(test[i])[0].detach().numpy(), model(test[i])[1:].detach().numpy()
        stars.append(StarSet(centers[i], bases[i], C.numpy(), torch.relu(model(test[i])).detach().numpy()*g.numpy()))

    return stars