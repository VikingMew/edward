from __future__ import print_function
import numpy as np
import tensorflow as tf

from edward.stats import bernoulli, beta, norm, dirichlet, invgamma
from edward.util import get_dims, concat


class MFMixGaussian:
    """
    q(z | lambda ) = Dirichlet(z | lambda1) * Gaussian(z | lambda2) * Inv_Gamma(z|lambda3)
    """
    def __init__(self, D, K):
        self.K = K
        self.dirich = MFDirichlet(K, K)
        self.gauss = MFGaussian(K*D)
        self.invgam = MFInvGamma(K*D)

        dirich_num_vars = self.dirich.num_vars
        gauss_num_vars = self.gauss.num_vars
        invgam_num_vars = self.invgam.num_vars
        self.num_vars = dirich_num_vars + gauss_num_vars + invgam_num_vars

        dirich_num_param = self.dirich.num_params
        gauss_num_param = self.gauss.num_params
        invgam_num_params = self.invgam.num_params
        self.num_params = dirich_num_param + gauss_num_param + invgam_num_params

    def print_params(self, sess):
    	self.dirich.print_params(sess)
        self.gauss.print_params(sess)
        self.invgam.print_params(sess)

    def sample(self, size, sess):
        """z ~ q(z | lambda)"""

        dirich_samples = self.dirich.sample((size[0],self.dirich.num_vars), sess)
        gauss_samples = self.gauss.sample((size[0], self.gauss.num_vars), sess)
        invgam_samples = self.invgam.sample((size[0], self.invgam.num_vars), sess)

        z = np.concatenate((dirich_samples[0][0], gauss_samples, invgam_samples[0]), axis=0)

        return z.reshape(size)

    def log_prob_zi(self, i, z):
        """log q(z_i | lambda_i)"""

        log_prob = 0
        if i < self.dirich.num_vars:
            log_prob += self.dirich.log_prob_zi(i, z)

        if i < self.gauss.num_vars:
            log_prob += self.gauss.log_prob_zi(i, z)

        if i < self.invgam.num_vars:
            log_prob += self.invgam.log_prob_zi(i, z)

        if i >= self.num_vars:
            raise

        return log_prob

class MFDirichlet:
    """
    q(z | lambda ) = prod_{i=1}^d Dirichlet(z[i] | lambda[i])
    """
    def __init__(self, num_vars, K):
        self.K = K
        self.num_vars = num_vars
        self.num_params = K * num_vars
        self.alpha_unconst = tf.Variable(tf.random_normal([num_vars, K]))
        self.transform = tf.nn.softplus

    def print_params(self, sess):
        alpha = sess.run([self.transform(self.alpha_unconst)])

        print("concentration vector:")
        print(alpha)

    def sample(self, size, sess):
        """z ~ q(z | lambda)"""
        alpha = sess.run([self.transform(self.alpha_unconst)])[0]
        z = np.zeros((size[1], size[0], self.K))
        for d in xrange(self.num_vars):
            z[d, :, :] = dirichlet.rvs(alpha[d, :], size = size[0])

        return z

    def log_prob_zi(self, i, z):
        """log q(z_i | lambda_i)"""
        if i >= self.num_vars:
            raise

        alphai = self.transform(self.alpha_unconst)[i, :]

        return dirichlet.logpdf(z[:, i], alphai)

class MFInvGamma:
    """
    q(z | lambda ) = prod_{i=1}^d Inv_Gamma(z[i] | lambda[i])
    """
    def __init__(self, num_vars):
        self.num_vars = num_vars
        self.num_params = 2 * num_vars
        self.a_unconst = tf.Variable(tf.random_normal([num_vars]))
        self.b_unconst = tf.Variable(tf.random_normal([num_vars]))
        self.transform = tf.nn.softplus

    def print_params(self, sess):
        a, b = sess.run([ \
            self.transform(self.a_unconst),
            self.transform(self.b_unconst)])

        print("shape:")
        print(a)
        print("scale:")
        print(b)

    def sample(self, size, sess):
        """z ~ q(z | lambda)"""
        a, b = sess.run([ \
            self.transform(self.a_unconst),
            self.transform(self.b_unconst)])

        z = np.zeros(size)
        for d in range(self.num_vars):
            z[:, d] = invgamma.rvs(a[d], b[d], size=size[0])

        return z

    def log_prob_zi(self, i, z):
        """log q(z_i | lambda_i)"""
        if i >= self.num_vars:
            raise

        ai = self.transform(self.a_unconst)[i]
        bi = self.transform(self.b_unconst)[i]

        return invgamma.logpdf(z[:, i], ai, bi)

class MFBernoulli:
    """
    q(z | lambda ) = prod_{i=1}^d Bernoulli(z[i] | lambda[i])
    """
    def __init__(self, num_vars):
        self.num_vars = num_vars
        self.num_params = num_vars

        self.p_unconst = tf.Variable(tf.random_normal([num_vars]))
        # TODO make all variables outside, not in these classes but as
        # part of inference most generally
        self.transform = tf.sigmoid
        # TODO something about constraining the parameters in simplex
        # TODO deal with truncations

    # TODO use __str__(self):
    def print_params(self, sess):
        p = sess.run([self.transform(self.p_unconst)])[0]
        if p.size > 1:
            p[-1] = 1.0 - np.sum(p[:-1])

        print("probability:")
        print(p)

    def sample(self, size, sess):
        """z ~ q(z | lambda)"""
        p = sess.run([self.transform(self.p_unconst)])[0]
        if p.size > 1:
            p[-1] = 1.0 - np.sum(p[:-1])

        z = np.zeros(size)
        for d in range(self.num_vars):
            z[:, d] = bernoulli.rvs(p[d], size=size[0])

        return z

    def log_prob_zi(self, i, z):
        """log q(z_i | lambda_i)"""
        if i >= self.num_vars:
            raise

        if i < self.num_vars:
            pi = self.transform(self.p_unconst[i])
        else:
            pi = 1.0 - tf.reduce_sum(self.transform(self.p_unconst[-1]))

        return bernoulli.logpmf(z[:, i], pi)

class MFBeta:
    """
    q(z | lambda ) = prod_{i=1}^d Beta(z[i] | lambda[i])
    """
    def __init__(self, num_vars):
        self.num_vars = num_vars
        self.num_params = 2*num_vars

        self.a_unconst = tf.Variable(tf.random_normal([num_vars]))
        self.b_unconst = tf.Variable(tf.random_normal([num_vars]))
        self.transform = tf.nn.softplus

    def print_params(self, sess):
        a, b = sess.run([ \
            self.transform(self.a_unconst),
            self.transform(self.b_unconst)])

        print("shape:")
        print(a)
        print("scale:")
        print(b)

    def sample(self, size, sess):
        """z ~ q(z | lambda)"""
        a, b = sess.run([ \
            self.transform(self.a_unconst),
            self.transform(self.b_unconst)])

        z = np.zeros(size)
        for d in range(self.num_vars):
            z[:, d] = beta.rvs(a[d], b[d], size=size[0])

        return z

    def log_prob_zi(self, i, z):
        """log q(z_i | lambda_i)"""
        if i >= self.num_vars:
            raise

        ai = self.transform(self.a_unconst)[i]
        bi = self.transform(self.b_unconst)[i]
        # TODO
        #ai = self.transform(self.a_unconst[i])
        #bi = self.transform(self.b_unconst[i])
        return beta.logpdf(z[:, i], ai, bi)

class MFGaussian:
    """
    q(z | lambda ) = prod_{i=1}^d Gaussian(z[i] | lambda[i])
    """
    def __init__(self, num_vars):
        self.num_vars = num_vars
        self.num_params = 2*num_vars

        self.m_unconst = tf.Variable(tf.random_normal([num_vars]))
        self.s_unconst = tf.Variable(tf.random_normal([num_vars]))
        self.transform_m = tf.identity
        self.transform_s = tf.nn.softplus

    def print_params(self, sess):
        m, s = sess.run([ \
            self.transform_m(self.m_unconst),
            self.transform_s(self.s_unconst)])

        print("mean:")
        print(m)
        print("std dev:")
        print(s)

    def sample_noise(self, size):
        """
        eps = sample_noise() ~ s(eps)
        s.t. z = reparam(eps; lambda) ~ q(z | lambda)
        """
        # Not using this, since TensorFlow has a large overhead
        # whenever calling sess.run().
        #samples = sess.run(tf.random_normal(self.samples.get_shape()))
        return norm.rvs(size=size)

    def reparam(self, eps):
        """
        eps = sample_noise() ~ s(eps)
        s.t. z = reparam(eps; lambda) ~ q(z | lambda)
        """
        m = self.transform_m(self.m_unconst)
        s = self.transform_s(self.s_unconst)
        return m + eps * s

    def sample(self, size, sess):
        """
        z ~ q(z | lambda)
        """
        return self.reparam(self.sample_noise(size))

    def log_prob_zi(self, i, z):
        """log q(z_i | lambda_i)"""
        if i >= self.num_vars:
            raise

        mi = self.transform_m(self.m_unconst)[i]
        si = self.transform_s(self.s_unconst)[i]
        # TODO
        #mi = self.transform_m(self.m_unconst[i])
        #si = self.transform_s(self.s_unconst[i])
        return concat([norm.logpdf(zm[i], mi, si)
                       for zm in tf.unpack(z)])

    # TODO entropy is bugged
    #def entropy(self):
    #    return norm.entropy(self.transform_s(self.s_unconst))

class PointMass():
    """
    Point mass variational family
    """
    def __init__(self, num_vars, transform=tf.identity):
        self.num_vars = num_vars
        self.num_params = num_vars

        self.param_unconst = tf.Variable(tf.random_normal([num_vars]))
        self.transform = transform

    def print_params(self, sess):
        params = sess.run([self.transform(self.param_unconst)])
        print("parameter values:")
        print(params)

    def get_params(self):
        return self.transform(self.param_unconst)