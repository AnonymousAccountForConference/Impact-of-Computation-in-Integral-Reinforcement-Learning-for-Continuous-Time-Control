import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
from probnum.quad import bayesquad_from_data
from probnum.randprocs.kernels import Matern
from scipy.integrate import solve_ivp

from NN import phi_sin
from env import SinSystem

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Parameters for PN-ADP')
    parser.add_argument('--xn', type=int, default=2, help='Dimension of the state')
    parser.add_argument('--un', type=int, default=1, help='Dimension of the input')
    parser.add_argument('--num_points', type=int, default=2,
                        help='Num of the points for integration')
    parser.add_argument('--N', type=int, default=20,
                        help='Num of the row of the LS matrix, should be at least xn^2+2*xn*un')
    parser.add_argument('--T', type=float, default=0.1,
                        help='Time inverval')
    parser.add_argument('--epsilon', type=float, default=1e-3,
                        help='end condition for policy iteration')
    parser.add_argument('--max_iteration', type=int, default=100,
                        help='max iteration number')
    parser.add_argument('--phin', type=int, default=3, help='Dimension of the phi')
    parser.add_argument('--learn_type', type=str, default='Matern', help='analytical, trapz, Matern')

    args = parser.parse_args()
    args_dict = vars(args)

    env = SinSystem()

    # Initialization
    N = args_dict['N']
    T = args_dict['T']
    num_points = args_dict['num_points']
    xn = args_dict['xn']
    phin = args_dict['phin']
    epsilon = args_dict['epsilon']
    max_iteration = args_dict['max_iteration']
    learn_type = args_dict['learn_type']
    w_opt = env.wopt


    # Define the functions
    def policy(x):
        u = -1 / 2 * np.linalg.inv(env.R) @ env.g(x).T @ env.d_phi(x) @ w
        return u.flatten()


    def sample_env(t, X):
        x = X[0:xn]
        u = policy(x)
        x_dot = env.transition(x, u)
        l_dot = np.atleast_1d(x.T @ env.Q @ x + u.T @ env.R @ u)
        return np.concatenate((x_dot, l_dot), axis=0)


    # Set the parameters
    sample_interval = T / (num_points - 1)
    w = env.w0

    w_old = np.Inf * np.ones((phin, 1))

    iteration = 0
    X0 = np.append(env.x0, 0)
    while np.linalg.norm(w - w_old) >= epsilon and iteration < max_iteration:
        print()
        print('iter = :', iteration)
        print('error = :', np.linalg.norm(w - w_old))

        # Collect data
        I = np.zeros((N, 1))
        Phi = np.zeros((N, phin))

        for i in range(N):
            # init_t = 0
            init_t = i * T + iteration * N * T
            t_eval = np.linspace(init_t, init_t + T, num_points)
            t_span = [t_eval[0], t_eval[-1]]
            sol = solve_ivp(sample_env, t_span=t_span, y0=X0, method='RK45', t_eval=t_eval, rtol=1e-8, atol=1e-8)
            X0 = sol.y[:, -1]  # y: (xn+1, length)

            x_seq = sol.y[0:-1, :]
            u_seq = np.apply_along_axis(policy, axis=0, arr=x_seq)

            l_seq = []

            for t in range(x_seq.shape[1]):
                x_t = x_seq[:, t]
                u_t = u_seq[:, t]
                l_seq.append(x_t.T @ env.Q @ x_t + u_t.T @ env.R @ u_t)

            l_seq = np.array(l_seq)

            integral_analytical = sol.y[-1, -1] - sol.y[-1, 0]

            kernel = Matern(input_shape=1, nu=3.5, lengthscales=0.3)
            domain = (t_eval[0], t_eval[-1])
            nodes = np.atleast_2d(t_eval).T
            fun_evals = l_seq
            F, info = bayesquad_from_data(nodes=nodes, fun_evals=fun_evals, kernel=kernel, domain=domain)

            integral_Matern = F.mean

            if learn_type == 'analytical':
                I[i, :] = integral_analytical
            elif learn_type == 'trapz':
                I[i, :] = integral_trapz
            elif learn_type == 'Matern':
                I[i, :] = integral_Matern
            else:
                raise ValueError

            phi_end = phi_sin(x_seq[:, -1])
            phi_start = phi_sin(x_seq[:, 0])

            Phi[i, :] = phi_start - phi_end

        # Solve LS problem
        w_old = w
        w = np.linalg.pinv(Phi) @ I
        print('w-w_opt =', np.linalg.norm(w - w_opt))
        iteration += 1

    P = np.array([[w[0], 0.5 * w[1]], [0.5 * w[1], w[2]]])
    P_opt = np.array([[w_opt[0], 0.5 * w_opt[1]], [0.5 * w_opt[1], w_opt[2]]])

    # T_eval = 1000 * T
    # t_eval = np.arange(0, T_eval + 1e-10, sample_interval / 10)
    # t_span = [t_eval[0], t_eval[-1]]

    # J_seq = []
    # J_opt_seq = []
    #
    mean = np.zeros((xn,))
    cov = 10000 * np.eye(xn)
    #
    w_old = w.copy()

    # for MC in range(100):
    #     w = w_old
    #     samples = np.random.multivariate_normal(mean, cov)
    #     X0 = np.append(samples, 0)
    #     sol = solve_ivp(sample_env, t_span=t_span, y0=X0, method='RK45', t_eval=t_eval, rtol=1e-8, atol=1e-8)
    #     J = sol.y[-1, -1] - sol.y[-1, 0]
    #     J_seq.append(J)
    #     w = w_opt
    #     sol = solve_ivp(sample_env, t_span=t_span, y0=X0, method='RK45', t_eval=t_eval, rtol=1e-8, atol=1e-8)
    #     J_opt = sol.y[-1, -1] - sol.y[-1, 0]
    #     J_opt_seq.append(J_opt)
    #
    # J = np.mean(J_seq)
    # J_opt = np.mean(J_opt_seq)
    u_error_seq = []
    samples = np.random.multivariate_normal(mean, cov, 10000)

    for MC in range(10000):
        w = w_old
        u = policy(samples[MC])
        w = w_opt
        u_opt = policy(samples[MC])

        u_error_seq.append(np.abs(u - u_opt))

    u_error = np.mean(u_error_seq)

    folder_name = type(env).__name__ + '/Matern'
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
    filename = os.path.join(folder_name, f"data_{args_dict['num_points']:02}.npz")
    np.save(filename, (np.linalg.norm(w_old - w_opt), u_error, np.trace(P-P_opt)*10000))
