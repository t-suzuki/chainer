import numpy

from chainer import cuda
from chainer import function
from chainer.utils import type_check

if cuda.cudnn_enabled:
    cudnn = cuda.cudnn
    libcudnn = cudnn.cudnn
    _algorithm = libcudnn.CUDNN_SOFTMAX_LOG
    _mode = libcudnn.CUDNN_SOFTMAX_MODE_CHANNEL
    _cudnn_version = libcudnn.getVersion()


def logsumexp(x):
    xp = cuda.get_array_module(x)
    m = x.max(axis=1, keepdims=True)
    y = x - m
    xp.exp(y, out=y)
    return xp.log(y.sum(axis=1, keepdims=True)) + m


class LogSoftmax(function.Function):

    """Log-softmax activation function."""

    def __init__(self, use_cudnn=True):
        self.use_cudnn = use_cudnn

    def check_type_forward(self, in_types):
        type_check.expect(in_types.size() == 1)
        x_type, = in_types

        type_check.expect(
            x_type.dtype == numpy.float32,
            x_type.ndim > 1,
        )

    def forward(self, xs):
        x = xs[0]
        xp = cuda.get_array_module(x)
        if xp != numpy and cuda.cudnn_enabled and self.use_cudnn \
           and _cudnn_version >= 3000:
            dtype = x.dtype
            one = numpy.array(1, dtype=dtype).ctypes
            zero = numpy.array(0, dtype=dtype).ctypes
            handle = cudnn.get_handle()
            x_cube = x.reshape(x.shape[:2] + (-1, 1))
            desc = cudnn.create_tensor_descriptor(x_cube)
            self.y = xp.empty_like(x)
            libcudnn.softmaxForward(
                handle, _algorithm, _mode, one.data, desc.value,
                x_cube.data.ptr, zero.data, desc.value,
                self.y.data.ptr)
            return self.y,

        else:
            log_z = logsumexp(x)
            self.y = x - log_z
            return self.y,

    def backward(self, x, gy):
        xp = cuda.get_array_module(*x)
        if xp != numpy and cuda.cudnn_enabled and self.use_cudnn \
           and _cudnn_version >= 3000:
            dtype = x[0].dtype
            one = numpy.array(1, dtype=dtype).ctypes
            zero = numpy.array(0, dtype=dtype).ctypes
            handle = cudnn.get_handle()
            gx = xp.empty_like(x[0])
            gx_cube = gx.reshape(gx.shape[:2] + (-1, 1))
            desc = cudnn.create_tensor_descriptor(gx_cube)
            libcudnn.softmaxBackward(
                handle, _algorithm, _mode, one.data, desc.value,
                self.y.data.ptr, desc.value, gy[0].data.ptr, zero.data,
                desc.value, gx.data.ptr)
        else:
            gx = gy[0] - xp.exp(self.y) * gy[0].sum(axis=1, keepdims=True)

        return gx,


def log_softmax(x, use_cudnn=True):
    """Channelwise log-softmax function.

    This function computes its logarithm of softmax along the second axis. Let
    :math:`x = (x_1, x_2, \\dots, x_d)^{\\top}` be the d dimensional index
    array and :math:`f(x)` be the d dimensional input array. For each index
    :math:`x` of the input array :math:`f(x)`, it computes the probability
    :math:`\log p(x)` defined as
    :math:`p(x) = {\\exp(f(x)) \\over \\sum_{x_2} \\exp(f(x))}`.

    Note that `log(softmax(x))` may cause underflow when ``x`` is too small,
    because ``softmax(x)`` may returns 0.
    `log_softmax` method is more stable.

    Args:
        x (~chainer.Variable): Input variable.
        use_cudnn (bool): If True and cuDNN is enabled, then this function uses
            cuDNN as the core implementation.

    Returns:
        ~chainer.Variable: Output variable.

    """
    return LogSoftmax(use_cudnn)(x)
