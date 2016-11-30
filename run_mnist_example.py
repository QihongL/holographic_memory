import os
import math
import tensorflow as tf
import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt

from hm import HolographicMemory
from mnist_number import MNIST_Number, full_mnist
from utils import one_hot
from sklearn.preprocessing import normalize

#################################################################################################
#                             Configuration parameters & Defaults                               #
#################################################################################################
flags = tf.flags
flags.DEFINE_integer("num_copies", 3, "Number of copies to make.")
flags.DEFINE_integer("batch_size", 2, "Number of samples to use in minibatch")
flags.DEFINE_integer("seed", None, "Fixed seed to get reproducible results.")
flags.DEFINE_string("keytype", "normal", "Use N(0, I) keys")
flags.DEFINE_bool("pseudokeys", 1, "Use synthetically generated keys or [data + error] as keys")
flags.DEFINE_bool("complex_normalize_keys", 0, "Normalize keys via complex mod.")
flags.DEFINE_bool("l2_normalize_keys", 0, "Normalize keys via l2 norm.")
flags.DEFINE_string("device", "/gpu:0", "Compute device.")
flags.DEFINE_boolean("allow_soft_placement", False, "Soft device placement.")
flags.DEFINE_float("device_percentage", 0.8, "Amount of memory to use on device.")
FLAGS = flags.FLAGS
#################################################################################################

def save_fig(m, name):
    plt.figure()
    plt.imshow(m.reshape(28, 28))
    plt.savefig(name, bbox_inches='tight')
    plt.close()

def gen_unif_keys(input_size, batch_size, seed):
    assert input_size % 2 == 0
    keys = [tf.Variable(tf.random_uniform([1, input_size],
                                          seed=seed*17+2*i if seed else None), #XXX
                        trainable=False, name="key_%d"%i) for i in range(batch_size)]
    return keys

def gen_std_keys(input_size, batch_size, seed):
    assert input_size % 2 == 0
    keys = [tf.Variable(tf.random_normal([1, input_size],
                                         seed=seed*17+2*i if seed else None, #XXX
                                         stddev=1.0/batch_size),
                        trainable=False, name="key_%d"%i) for i in range(batch_size)]
    return keys


def gen_onehot_keys(input_size, batch_size):
    keys = [tf.Variable(tf.constant(one_hot(input_size, [i]), dtype=tf.float32),
                        trainable=False, name="key_%d"%i) for i in range(batch_size)]
    return keys

def generate_keys(keytype, input_size, batch_size, seed):
    if keytype == 'onehot':
        keys = gen_onehot_keys(input_size, batch_size)
    elif keytype == 'normal' or 'std':
        keys = gen_std_keys(input_size, batch_size, seed)
    elif keytype == 'unif':
        keys = gen_unif_keys(input_size, batch_size, seed)
    else:
        raise Exception("undefined key type")

    return keys

def main():
    # create a tf session and the holographic memory object
    with tf.device(FLAGS.device):
        gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=FLAGS.device_percentage)
        with tf.Session(config=tf.ConfigProto(allow_soft_placement=FLAGS.allow_soft_placement,
                                              gpu_options=gpu_options)) as sess:
            input_size = 784  # MNIST input size [28, 28]

            # initialize our holographic memory
            memory = HolographicMemory(sess, input_size, FLAGS.batch_size, FLAGS.num_copies, seed=FLAGS.seed)

            # Generate some random values & save a test sample
            #minibatch, labels = MNIST_Number(0, full_mnist).get_batch_iter(FLAGS.batch_size)
            minibatch, labels = full_mnist.train.next_batch(FLAGS.batch_size)
            value = tf.constant(minibatch, dtype=tf.float32, name="minibatch")

            # There are num_copies x [1 x num_features] keys
            # They are generated by either:
            #     1) Randomly Generated [FLAGS.pseudokeys=True]
            #     2) From a noisy version of the data
            if FLAGS.pseudokeys:
                print 'generating pseudokeys...'
                keys = generate_keys(FLAGS.keytype, input_size, FLAGS.batch_size, FLAGS.seed)
            else:
                print 'utilizing real data + N(0,I) as keys...'
                keys = [tf.add(v, tf.random_normal(v.get_shape().as_list()), name="keys_%d"%i)
                        for v, i in zip(tf.split(0, minibatch.shape[0], value), range(minibatch.shape[0]))]

            # Normalize our keys to mod 1 if specified
            if FLAGS.complex_normalize_keys:
                keys = HolographicMemory.normalize_real_by_complex_abs(keys)

            # Normalize our keys using the l2 norm
            if FLAGS.l2_normalize_keys:
                keys = [tf.nn.l2_normalize(k, 1) for k in keys]

            sess.run(tf.initialize_all_variables())

            # do a little validation on the keys
            if FLAGS.complex_normalize_keys and FLAGS.keytype != 'onehot':
                memory.verify_key_mod(keys)

            # Get some info on the original data
            print 'values to encode : ', str(minibatch.shape)
            for i in range(len(minibatch)):
                save_fig(minibatch[i], "imgs/original_%d.png" %i)

            # encode value with the keys
            memories = memory.encode(value, keys)
            memories_host = sess.run(memories)
            print 'encoded memories shape = %s' \
                % (str(memories_host.shape))
            #print 'em = ', memories_host

            # recover all the values from the minibatch
            # Run list comprehension to get a list of tensors and run them in batch
            values_recovered = [tf.reduce_sum(memory.decode(memories, [keys[i]]), 0) for i in range(len(keys))]
            values_recovered_host = sess.run(values_recovered)

            for val, j in zip(values_recovered_host, range(len(values_recovered_host))):
                save_fig(val, "imgs/recovered_%d.png"  % j)
                #save_fig (normalize(val, axis=0), "imgs/recovered_%d.png"  % j)
                print 'recovered value shape = ', val.shape
                #print 'recovered value [%s] = %s\n' % (val.shape, val)

if __name__ == "__main__":
    # Create our image directories
    if not os.path.exists('imgs'):
        os.makedirs('imgs')

    # Execute main loop
    main()
