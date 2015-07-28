import ctypes
import numpy

from chainer import cuda
from chainer.cuda import cudnn
from chainer import function
from chainer.utils import type_check

if cudnn.available:
    libcudnn = cudnn.cudnn
    _mode = libcudnn.CUDNN_ACTIVATION_TANH


class Tanh(function.Function):

    """Hyperbolic tangent function."""

    def __init__(self, use_cudnn=True):
        self.use_cudnn = use_cudnn

    def check_type_forward(self, in_types):
        type_check.expect(in_types.size() == 1)
        type_check.expect(in_types[0].dtype == numpy.float32)

    def forward_cpu(self, x):
        self.y = numpy.tanh(x[0])
        return self.y,

    def forward_gpu(self, x):
        self.y = cuda.empty_like(x[0])
        if cuda.cudnn_enabled and self.use_cudnn:
            handle = cudnn.get_handle()
            x_mat = x[0].reshape(x[0].shape[0], -1, 1, 1)
            desc = cudnn.create_tensor_descriptor(x_mat)
            libcudnn.activationForward(
                handle, _mode, ctypes.c_float(1), desc.value, x_mat.data.ptr,
                ctypes.c_float(0), desc.value, self.y.data.ptr)
        else:
            cuda.cupy.tanh(x[0], out=self.y)
        return self.y,

    def backward_cpu(self, x, gy):
        return gy[0] * (1 - self.y * self.y),

    def backward_gpu(self, x, gy):
        gx = cuda.empty_like(self.y)
        if cuda.cudnn_enabled and self.use_cudnn:
            handle = cudnn.get_handle()
            y_mat = self.y.reshape(self.y.shape[0], -1, 1, 1)
            desc = cudnn.create_tensor_descriptor(y_mat)
            libcudnn.activationBackward(
                handle, _mode, ctypes.c_float(1), desc.value, y_mat.data.ptr,
                desc.value, gy[0].data.ptr, desc.value, x[0].data.ptr,
                ctypes.c_float(0), desc.value, gx.data.ptr)
        else:
            cuda.elementwise(
                ['gx', 'y', 'gy'],
                'gx[i] = gy[i] * (1 - y[i] * y[i])',
                'tanh_bwd')(gx, self.y, gy[0])
        return gx,


def tanh(x, use_cudnn=True):
    """Elementwise hyperbolic tangent function.

    Args:
        x (~chainer.Variable): Input variable.
        use_cudnn (bool): If True and CuDNN is enabled, then this function uses
            CuDNN as the core implementation.

    Returns:
        ~chainer.Variable: Output variable.

    """
    return Tanh(use_cudnn)(x)
