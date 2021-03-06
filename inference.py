from iostream import load_image
import numpy as np
import time


class Evaluation:
    def __init__(self):
        self.performance = None
        self.domain_accuracy = None
        # storage
        self.dice = []
        self.jaccard = []
        self.precision = []
        self.recall = []
        # additional
        self.accuracy = []
        for _ in range(8):
            self.dice.append([])
            self.jaccard.append([])
            self.precision.append([])
            self.recall.append([])

    def add(self, dice, jaccard, precision, recall):
        for i in range(8):
            self.dice[i].append(dice[i])
            self.jaccard[i].append(jaccard[i])
            self.precision[i].append(precision[i])
            self.recall[i].append(recall[i])

    def add_domain(self, domain_accuracy):
        self.accuracy.append(domain_accuracy)

    def retrieve(self):
        # shape: (4, 8, 1)
        self.performance = np.array([self.dice, self.jaccard, self.precision, self.recall], dtype='float32')
        return np.mean(self.performance, axis=2)

    def retrieve_domain(self):
        # shape: (1,)
        self.domain_accuracy = np.array(self.accuracy, dtype='float32')
        return np.mean(self.domain_accuracy, axis=0)


# a passing network
def network(_, label, domain):
    # input is a numpy array
    return label.copy(), domain.copy()


def compute_performance(inference, label, class_num):
    # all criterion
    dice = []
    jaccard = []
    precision = []
    recall = []

    start_time = time.time()
    for i in range(class_num):
        i_inference = 1 * (inference[:, :, :, :] == i)
        i_label = 1 * (label[:, :, :, :] == i)
        sum_label = np.sum(i_label)
        sum_inference = np.sum(i_inference)
        sum_intersection = np.sum(i_inference * i_label)
        # dice
        summation = sum_inference + sum_label + 1e-5
        i_dice = 2 * sum_intersection / summation
        # jaccard
        addition = i_inference + i_label
        union = np.sum(1 * (addition[:, :, :, :] > 0)) + 1e-5
        i_jaccard = sum_intersection / union
        # precision, recall
        i_precision = sum_intersection / (sum_inference + 1e-5)
        i_recall = sum_intersection / (sum_label + 1e-5)
        # separate storing!
        print(f'{i}: {i_dice} {i_jaccard} {i_precision} {i_recall}')
        dice.append(i_dice)
        jaccard.append(i_jaccard)
        precision.append(i_precision)
        recall.append(i_recall)
    # time reduction needed
    print(f'Estimate time: {time.time() - start_time}')
    return dice, jaccard, precision, recall


def compute_domain_performance(discrimination, domain_label):
    correct = 1 * (discrimination[:] == domain_label)
    accuracy = np.sum(correct) / (discrimination.shape[0] + 1e-5)
    print(f'Domain accuracy: {accuracy}')
    return accuracy


def infer(image, label, domain, input_size=32, stride=32, channel=1,
          infer_task=None, coefficient=None, loss_log=None, evaluation=None, sample=None):

    # # fast forwarding: 32, center-cropping: 16
    # stride, equivalent to effective

    # skip
    stride_skip = (input_size - stride) // 2
    depth, height, width = image.shape

    # axis expansion
    image = np.expand_dims(image, axis=0)
    image = np.expand_dims(image, axis=4)
    label = np.expand_dims(label, axis=0)
    # initialization with -1
    discrimination = []
    inference = -1 * np.ones(label.shape, label.dtype)
    image_batch = np.zeros([1, input_size, input_size, input_size, channel], dtype='float32')
    label_batch = np.zeros([1, input_size, input_size, input_size], dtype='int32')
    # degenerate domain batch
    domain_batch = np.array([domain], dtype=np.int32)

    # -1 symbol for last
    depth_range = np.append(np.arange(depth - input_size + 1, step=stride), -1)
    height_range = np.append(np.arange(height - input_size + 1, step=stride), -1)
    width_range = np.append(np.arange(width - input_size + 1, step=stride), -1)

    start_time = time.time()
    for d in depth_range:
        for h in height_range:
            for w in width_range:
                # default situation
                fetch_d, fetch_h, fetch_w = d, h, w  # fetch variable for the last batch
                put_d, put_h, put_w = d + stride_skip, h + stride_skip, w + stride_skip  # put for inference position
                size_d, size_h, size_w = input_size - stride_skip, input_size - stride_skip, input_size - stride_skip
                # for inference length

                if d == -1:
                    if depth % stride == 0:
                        continue
                    else:
                        fetch_d = depth - input_size
                        size_d = depth % stride
                        put_d = depth - size_d
                elif d == 0:
                    put_d = d
                    size_d = input_size

                if h == -1:
                    if height % stride == 0:
                        continue
                    else:
                        fetch_h = height - input_size
                        size_h = height % stride
                        put_h = height - size_h
                elif h == 0:
                    put_h = h
                    size_h = input_size

                if w == -1:
                    if width % stride == 0:
                        continue
                    else:
                        fetch_w = width - input_size
                        size_w = width % stride
                        put_w = width - size_w
                elif w == 0:
                    put_w = w
                    size_w = input_size

                # batch cropping
                image_batch[0, :, :, :, 0] = image[0, fetch_d:fetch_d + input_size, fetch_h:fetch_h + input_size,
                                                   fetch_w:fetch_w + input_size, 0]
                label_batch[0, :, :, :] = label[0, fetch_d:fetch_d + input_size, fetch_h:fetch_h + input_size,
                                                fetch_w:fetch_w + input_size]

                # main body of network
                if infer_task is None:
                    infer_batch, infer_domain = network(image_batch, label_batch, domain_batch)
                else:
                    infer_batch, infer_domain = infer_task(
                        image_batch, label_batch, domain_batch, coefficient, loss_log,
                        fetch_d / depth, fetch_h / height, fetch_w / width, sample)

                # fast forwarding
                inference[0, put_d:put_d + size_d, put_h:put_h + size_h, put_w:put_w + size_w] = \
                    infer_batch[0, -size_d:, -size_h:, -size_w:]
                discrimination.append(infer_domain[:])

    discrimination = np.array(discrimination, dtype='int32')

    print('Running time:', time.time() - start_time)
    # print('image:', image.shape)
    # print('label:', label.shape)
    # print('inference:', inference.shape)
    # print(f'stride: {stride}, equal: {np.array_equal(inference, label)}', )
    accuracy = compute_domain_performance(discrimination, domain)
    dice, jaccard, precision, recall = compute_performance(inference, label, 8)
    evaluation.add(dice, jaccard, precision, recall)
    evaluation.add_domain(accuracy)

    return inference


if __name__ == '__main__':
    img, truth = load_image('../MM-WHS/ct_train/ct_train_1001_image.nii.gz',
                            '../MM-WHS/ct_train/ct_train_1001_label.nii.gz')
    print('image:', img.shape)
    print('label:', truth.shape)
    e = Evaluation()
    infer(img, truth, 0, stride=32, evaluation=e)
    print(e.retrieve().shape)
    print(e.retrieve_domain().shape)
    print(str(e.retrieve()))
    print(str(e.retrieve_domain()))
