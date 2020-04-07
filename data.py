# -*- coding: utf-8 -*-
"""
Created on Thu Feb 13 11:11:52 2020

@author: Kevin

Various methods used for image pre- and post-processing.

Potential future work: alter generate_density_map to deal with dessicated eggs - read in class type, draw healthy eggs
    on first channel and dessicated on second channel. Will require higher resolution image (current default of 480p
    is insufficient to distinguish between the two cases), modifying and re-training EggCountNet for two output classes.
"""
import os
import cv2
import numpy as np
import matplotlib.pyplot as plt
from win32api import GetSystemMetrics
import tkinter as tk
from tkinter import filedialog
from scipy.ndimage import gaussian_filter
from tqdm import tqdm
from os.path import exists

cropping = False
cropped = False
x_start, y_start, x_end, y_end = 0, 0, 0, 0


def mouse_crop(event, x, y, flags, param):
    """
    Grabs mouse coordinates from image display frame at commencement of cropping and end. Feeds to global coordinates
    for further use.
    """
    # grab references to the global variables
    global x_start, y_start, x_end, y_end, cropping, cropped

    # if the left mouse button was DOWN, start RECORDING
    # (x, y) coordinates and indicate that cropping is being
    if event == cv2.EVENT_LBUTTONDOWN:
        x_start, y_start, x_end, y_end = x, y, x, y
        cropping = True

    # Mouse is Moving
    elif event == cv2.EVENT_MOUSEMOVE:
        if cropping:
            x_end, y_end = x, y

    # if the left mouse button was released
    elif event == cv2.EVENT_LBUTTONUP:
        # record the ending (x, y) coordinates
        x_end, y_end = x, y
        cropping = False  # cropping is finished

        ref_point = [(x_start, y_start), (x_end, y_end)]

        if len(ref_point) == 2:  # when two points were found, display cropped image
            cropped = True


def yolo_to_xy(yolo_txt, img_dim):
    """
    Takes in coordinates in YOLO format. Converts to raw pixel # format

    Arg:
        yolo_txt:   data in YOLO format (class, x, y, w, h) format
                    *** x, y, w, h are all expressed as percentages
        img_dim:    img shape (y_len, x_len)

    Returns:
        coor_format:       np array of coordinates of eggs (x, y)
    """
    coor_format = yolo_txt[:, 1:3]  # extract (x, y) coordinate info
    coor_format = coor_format * (-1) + 1  # 180 degree rotation
    coor_format[:, 0] *= img_dim[1]  # transforming percentages to coordinates
    coor_format[:, 1] *= img_dim[0]
    coor_format = coor_format.astype(int)  # round to int
    return coor_format


def image_rescale(img, final_dim):
    """
    Takes in image and desired final dimensions. Returns rescaled image and the
    rescale factor for further calculations.

    Args:
        img:        input image to be rescaled
        final_dim:  final dimensions of image (width, height)

    Returns:
        img_rescaled
        rescale_factor:     rescale factor (r_f_x, r_f_y)
    """
    rescale_factor = (final_dim[0] / img.shape[1], final_dim[1] / img.shape[0])
    img_rescaled = cv2.resize(img, final_dim)
    return img_rescaled, rescale_factor


def coor_rescale(original_coordinates, rescale_factor):
    """
    Rescales coordinates based of rescaling factor.

    Args:
        original_coordinates:   coordinates of eggs in (x, y) format
        rescale_factor:         rescale factor (r_f_x, r_f_y)

    Return:
        coordinates_rescaled:  coordinates in rescaled image space
    """
    coordinates_rescaled = np.zeros_like(original_coordinates)
    coordinates_rescaled[:, 0] = original_coordinates[:, 0] * rescale_factor[0]
    coordinates_rescaled[:, 1] = original_coordinates[:, 1] * rescale_factor[1]
    coordinates_rescaled = coordinates_rescaled.astype(int)
    return coordinates_rescaled


def coor_crop_shift(original_coordinates, cropped_image_corners):
    """
    Converts coordinates in original image space to coordinates in cropped
    image space.

    Args:
        original_coordinates:   egg coordinates of original image (x, y)
        cropped_image_corners:  cropped image coordinates [(x_start, y_start), (x_end, y_end)]

    Returns:
        cropped_coordinates:    coordinates in cropped image space (x, y)
    """
    cropped_coordinates = np.zeros([0, 2])
    min_x = min(cropped_image_corners[0][0], cropped_image_corners[1][0])
    max_x = max(cropped_image_corners[0][0], cropped_image_corners[1][0])
    min_y = min(cropped_image_corners[0][1], cropped_image_corners[1][1])
    max_y = max(cropped_image_corners[0][1], cropped_image_corners[1][1])
    for i in range(original_coordinates.shape[0]):
        if min_x <= original_coordinates[i, 0] <= max_x and min_y <= original_coordinates[i, 1] <= max_y:
            cropped_coordinates = np.append(cropped_coordinates, [[original_coordinates[i, 0] - min_x,
                                                                   original_coordinates[i, 1] - min_y]], axis=0)
    return cropped_coordinates


def draw_points_on_image(image, coordinates):
    """
    Sanity check: draws dot on image at location of egg

    Args:
        image:
        coordinates:

    Returns:
        None
    """
    paint = [0, 255, 0]
    for i in range(coordinates.shape[0]):
        image[coordinates[i, 1], coordinates[i, 0]] = paint
        image[coordinates[i, 1] + 1, coordinates[i, 0]] = paint
        image[coordinates[i, 1] - 1, coordinates[i, 0]] = paint
        image[coordinates[i, 1], coordinates[i, 0] + 1] = paint
        image[coordinates[i, 1], coordinates[i, 0] - 1] = paint

    plt.imshow(image)
    plt.show()

    return None


def generate_density_map(img_path: str, coor_path: str):
    """
    Generate a density map based on objects positions.

    Args:
        img_path (str):     location of image
        coor_path (str):    location of txt file containing coordinate info in (x, y) format

    Returns:
        density_map:        density map of inputted image
    """

    assert img_path.rstrip('.JPG') == coor_path.rstrip('.txt'), 'img_path and coor_path files do not match'

    img = cv2.imread(img_path)
    coor = np.loadtxt(coor_path)
    coor = coor.astype(int)  # round to int
    # initialise density map of size image - only 1 channel
    density_map = np.zeros((img.shape[0], img.shape[1]), dtype=np.float32)

    # applying heat of 100 at location of eggs
    if coor.size > 0:
        for i in range(coor.shape[0]):
            density_map[coor[i, 1], coor[i, 0]] += 100

    # apply Gaussian kernel to density map
    density_map = gaussian_filter(density_map, sigma=(1, 1), order=0)
    return density_map


def generate_density_dot_map(img_path: str, coor_path: str):
    """
    Generate a density map based on objects positions.

    Args:
        img_path (str):     location of image
        coor_path (str):    location of txt file containing coordinate info in (x, y) format

    Returns:
        density_dot_map:    density map of inputted image in binary (1 for egg, 0 for empty space)
    """

    assert img_path.rstrip('.JPG') == coor_path.rstrip('.txt'), 'img_path and coor_path files do not match'

    img = cv2.imread(img_path)
    coor = np.loadtxt(coor_path)
    coor = coor.astype(int)  # round to int
    # initialise density map of size image - only 1 channel
    density_dot_map = np.zeros((img.shape[0], img.shape[1]), dtype=bool)

    # applying heat of 100 at location of eggs
    for i in range(coor.shape[0]):
        density_dot_map[coor[i, 1], coor[i, 0]] = 1
    return density_dot_map


def cropped_box_shift(corners, desired_aspect_ratio):
    """
    Adjusts corner coordinates of a box to match desired aspect ratio so as not to distort the image. This is achieved
    by increasing either the height or width of the box coordinates to capture more of the image.

    Args:
        corners (list of (tuples)):     input box coordinates [(x_start, y_start), (x_end, y_end)]
        desired_aspect_ratio (float):   aspect ratio (width / height) of output box

    Returns:
        adjusted_corners (list of (tuples)):    adjusted [(x_start, y_start), (x_end, y_end)]
    """
    [(x1, y1), (x2, y2)] = corners
    xc = (x1 + x2) / 2
    yc = (y1 + y2) / 2
    w = abs(x2 - x1)
    h = abs(y2 - y1)
    ar = w / h
    if ar >= desired_aspect_ratio:
        # input box too wide - increase height
        new_h = w / desired_aspect_ratio
        y1 = int(yc - (new_h / 2))
        y2 = int(yc + (new_h / 2))
    elif ar < desired_aspect_ratio:
        # input box too tall - increase width
        new_w = h * desired_aspect_ratio
        x1 = int(xc - (new_w / 2))
        x2 = int(xc + (new_w / 2))

    adjusted_corners = [(x1, y1), (x2, y2)]
    return adjusted_corners


def image_crop_and_scale(resolution: str = "480p"):
    """
    Prompts user to crop image in the section in which eggs exist. Unless specified, crops to 640x480p. Saves cropped
    image as .JPG

    Args:
        resolution:     desired output image's resolution

    Returns:
        None
    """
    global cropping, cropped, x_start, y_start, x_end, y_end
    cropping = False
    cropped = False
    x_start, y_start, x_end, y_end = 0, 0, 0, 0

    res = {"240p": (320, 240),
           "360p": (480, 360),
           "480p": (640, 480),
           "720p": (960, 720),
           "1080p": (1440, 1080)}
    res_tuple = res[resolution]
    aspect_ratio = res_tuple[0] / res_tuple[1]

    img_path = get_image_path()
    image = cv2.imread(img_path)

    # retrieving current display size to ensure it fits the screen during cropping and by inputted resolution for
    # image processing - format: (width, height)
    p_current_display = (GetSystemMetrics(0), GetSystemMetrics(1))

    # ensuring linear rescaling that fits user's window
    rf_crop_display = min(p_current_display[1] / image.shape[0], p_current_display[0] / image.shape[1])
    p_crop_display = (int(rf_crop_display * image.shape[1]), int(rf_crop_display * image.shape[0]))
    image_rescaled, rf_rescaled = image_rescale(image, p_crop_display)  # rescale to fit screen

    cv2.namedWindow("image")
    cv2.setMouseCallback("image", mouse_crop)
    while not cropped:
        image_copy = image_rescaled.copy()
        if not cropping:
            cv2.imshow("image", image_rescaled)
        elif cropping:
            cv2.rectangle(image_copy, (x_start, y_start), (x_end, y_end), (255, 0, 0), 2)
            cv2.imshow("image", image_copy)
        cv2.waitKey(1)
    # close all open windows
    cv2.destroyAllWindows()

    # Grabs coordinates of cropped image corners, creates cropped image, and creates shifts coordinates to cropped image
    # space.
    cropped_corners = [(x_start, y_start), (x_end, y_end)]
    cropped_corners = cropped_box_shift(cropped_corners, aspect_ratio)
    image_cropped = image_rescaled[cropped_corners[0][1]:cropped_corners[1][1],
                                   cropped_corners[0][0]:cropped_corners[1][0]]

    # Final downscaling to 480p format of both cropped image and coordinates for U-Net to process more easily.
    image_final_res, rf_final_res = image_rescale(image_cropped, res_tuple)

    return image_final_res


def image_crop_scale_dmap(resolution: str = "480p", img_path: str = ""):
    """
    Prompts user to select an image to crop. Scales the image to the input resolution (extends smallest dimension
        between height and width to do so). Saves cropped image with the coordinates of eggs within that cropped image.
        Generates density map, and saves that too.
    Args:
        resolution:         desired resolution of final image
        img_path:           directory path of where image is at

    Returns:
        img_path:           path of the original image that user selected
        image_final_res:    cropped image
        coor_final_res:     coordinates of eggs within cropped image
        dmap:               density map of cropped image
    """
    global cropping, cropped, x_start, y_start, x_end, y_end
    cropping = False
    cropped = False
    x_start, y_start, x_end, y_end = 0, 0, 0, 0

    res = {"240p": (320, 240),
           "360p": (480, 360),
           "480p": (640, 480),
           "720p": (960, 720),
           "1080p": (1440, 1080)}
    res_tuple = res[resolution]
    aspect_ratio = res_tuple[0] / res_tuple[1]

    # checks if img_path was given, if not, prompts user for path
    if not img_path:
        img_path = get_image_path()

    data_path = img_path[:-4] + ".txt"

    image = cv2.imread(img_path)
    data = np.loadtxt(data_path)
    coor = yolo_to_xy(data, image.shape)

    # get current display size to ensure image fits within user's current screen
    p_current_display = (GetSystemMetrics(0), GetSystemMetrics(1))
    rf_crop_display = min(p_current_display[1] / image.shape[0], p_current_display[0] / image.shape[1])
    p_crop_display = (int(rf_crop_display * image.shape[1]), int(rf_crop_display * image.shape[0]))
    image_rescaled, rf_rescaled = image_rescale(image, p_crop_display)  # rescale to fit screen
    coor_rescaled = coor_rescale(coor, rf_rescaled)  # updating coordinates of rescaled image

    cv2.namedWindow("image")
    cv2.setMouseCallback("image", mouse_crop)
    while not cropped:
        image_copy = image_rescaled.copy()
        if not cropping:
            cv2.imshow("image", image_rescaled)
        elif cropping:
            cv2.rectangle(image_copy, (x_start, y_start), (x_end, y_end), (255, 0, 0), 2)
            cv2.imshow("image", image_copy)
        cv2.waitKey(1)
    # close all open windows
    cv2.destroyAllWindows()

    # Grabs coordinates of cropped image corners, creates cropped image, and creates shifts coordinates to cropped image
    # space.
    cropped_corners = [(x_start, y_start), (x_end, y_end)]
    cropped_corners = cropped_box_shift(cropped_corners, aspect_ratio)
    [(x_start, y_start), (x_end, y_end)] = cropped_corners
    image_cropped = image_rescaled[cropped_corners[0][1]:cropped_corners[1][1],
                                   cropped_corners[0][0]:cropped_corners[1][0]]
    coor_cropped = coor_crop_shift(coor_rescaled, cropped_corners)

    # sanity check: ensuring all coordinates are within bounds of cropped image space
    assert min(coor_cropped[:, 0]) >= 0, "min(x) out of image"
    assert max(coor_cropped[:, 0]) <= abs(x_end - x_start), "max(x) out of image"
    assert min(coor_cropped[:, 1]) >= 0, "min(y) out of image"
    assert max(coor_cropped[:, 1]) <= abs(y_end - y_start), "max(y) out of image"

    # Final downscaling to 480p format of both cropped image and coordinates for U-Net to process more easily.
    image_final_res, rf_final_res = image_rescale(image_cropped, res_tuple)
    coor_final_res = coor_rescale(coor_cropped, rf_final_res)

    # Visual check that coordinates are at correct locations
    draw_points_on_image(image_final_res.copy(), coor_final_res)

    save_path = img_path[:-4]
    img_path_save = save_path + "_" + resolution + ".JPG"
    coor_path_save = save_path + "_" + resolution + ".txt"
    dmap_path_save = save_path + "_" + resolution + "_dmap.txt"
    cv2.imwrite(img_path_save, image_final_res)
    np.savetxt(coor_path_save, coor_final_res)

    dmap = generate_density_map(img_path_save, coor_path_save)
    np.savetxt(dmap_path_save, dmap)
    return img_path, image_final_res, coor_final_res, dmap


def image_down_res_dmap(resolution: str = "360p", img_path: str = ""):
    """
        Prompts user to select an image to crop. Downscales the image to the input resolution (extends smallest
            dimension between height and width to do so). Saves downscaled image with the coordinates of eggs within
            that downscaled image in (pixel_x, pixel_y) format. Generates density map, and saves that too.
        Args:
            resolution:         desired resolution of final image
            img_path:           directory path of where image is at

        Returns:
            img_path:           path of the original image that user selected
            image_final_res:    cropped image
            coor_final_res:     coordinates of eggs within cropped image
            dmap:               density map of cropped image
        """
    global cropping, cropped, x_start, y_start, x_end, y_end
    cropping = False
    cropped = False
    x_start, y_start, x_end, y_end = 0, 0, 0, 0

    res = {"240p": (320, 240),
           "360p": (480, 360),
           "480p": (640, 480),
           "720p": (960, 720),
           "1080p": (1440, 1080)}
    res_tuple = res[resolution]

    # checks if img_path was given, if not, prompts user for path
    if not img_path:
        img_path = get_image_path()

    data_path = img_path[:-4] + ".txt"

    image = cv2.imread(img_path)
    coor = np.loadtxt(data_path)

    img_downscaled, rf_downscale = image_rescale(image, res_tuple)
    coor_downscaled = coor_rescale(coor, rf_downscale)

    # Visual check that coordinates are at correct locations
    draw_points_on_image(img_downscaled.copy(), coor_downscaled)

    save_path = img_path[:-8]
    img_path_save = save_path + resolution + ".JPG"
    coor_path_save = save_path + resolution + ".txt"
    dmap_path_save = save_path + resolution + "_dmap.txt"
    cv2.imwrite(img_path_save, img_downscaled)
    np.savetxt(coor_path_save, coor_downscaled)

    dmap = generate_density_map(img_path_save, coor_path_save)
    np.savetxt(dmap_path_save, dmap)
    return img_path, img_downscaled, coor_downscaled, dmap


def heat_map(X_img, Y_img):
    """
    Sanity check to visually determine whether an image's density map matches up with ground truth.
    Args:
        X_img:  normal image of eggs
        Y_img:  density map
    """
    plt.figure()
    plt.subplot(1, 2, 1)
    plt.imshow(X_img)
    plt.subplot(1, 2, 2)
    plt.imshow(Y_img[:, :, 0], cmap='plasma')


def get_image_path():
    """
    Prompts user to navigate to and select .jpg file to be read.
    Returns:
        image_path (str):   path of valid image location
    """
    root = tk.Tk()
    root.withdraw()
    valid_jpg_file = False
    while not valid_jpg_file:
        file_path = filedialog.askopenfile()
        image_path = file_path.name
        if image_path.__contains__(".jpg") or image_path.__contains__(".JPG"):
            valid_jpg_file = True

    return image_path


def load_train_val_data():
    """
    Load training images (X_train) and normalises them, as well as their density map (y_train)

    Returns:
        X_train (list of images):   training images in 480p format
        Y_train (list of images):   density maps of training images

    """
    X_train_files = get_file_list('egg_photos/train_full_mix/', "_360p.JPG") \
                + get_file_list('egg_photos/train_full_mix/', "_360p.jpg")

    X_size = cv2.imread(X_train_files[0]).shape
    Y_size = np.loadtxt(X_train_files[0][:-4] + "_dmap.txt").shape
    X_train = np.zeros((X_train_files.__len__(), X_size[0], X_size[1], X_size[2]))
    Y_train = np.zeros((X_train_files.__len__(), Y_size[0], Y_size[1], 1))
    for i in tqdm(range(X_train_files.__len__())):
        X_train[i] = cv2.imread(X_train_files[i])
        Y_train[i, :, :, 0] = np.loadtxt(X_train_files[i][:-4] + "_dmap.txt")

    X_val_files = get_file_list('egg_photos/val_full_mix/', "_360p.JPG") \
                  + get_file_list('egg_photos/val_full_mix/', "_360p.jpg")
    X_val = np.zeros((X_val_files.__len__(), X_size[0], X_size[1], X_size[2]))
    Y_val = np.zeros((X_val_files.__len__(), Y_size[0], Y_size[1], 1))
    for i in tqdm(range(X_val_files.__len__())):
        X_val[i] = cv2.imread(X_val_files[i])
        Y_val[i, :, :, 0] = np.loadtxt(X_val_files[i][:-4] + "_dmap.txt")

    X_train = X_train.astype('float32')
    Y_train = Y_train.astype('float32')
    X_train /= 255.
    X_val = X_val.astype('float32')
    Y_val = Y_val.astype('float32')
    X_val /= 255.
    return X_train, Y_train, X_val, Y_val


def load_test_data():
    """
    Load test images

    Returns:
        X_test  (list of images):   test images
    """
    X_files = get_file_list('egg_photos/test/', "_360p.JPG") + get_file_list('egg_photos/test/', "_360p.jpg")
    X_size = cv2.imread(X_files[0]).shape
    X_test = np.zeros((X_files.__len__(), X_size[0], X_size[1], X_size[2]))
    for i in tqdm(range(len(X_files))):
        X_test[i] = cv2.imread(X_files[i])

    X_test = X_test.astype('float32')
    X_test /= 255
    return X_test


def generate_negative_controls(directory: str = "egg_photos/train_neg_augmented"):
    """
    Generates 480p resolution images of all images within directory
    """
    files = get_file_list(directory, ".jpg")
    Y_empty = np.zeros((360, 480))
    for f in files:
        print(f)
        img = cv2.imread(f)
        img_rescaled, rf = image_rescale(img, (480, 360))
        cv2.imwrite(f[:-4] + "_360p" + f[-4:], img_rescaled)
        np.savetxt(f[:-4] + "_360p_dmap.txt", Y_empty)


def get_file_list(path: str, search_term: str):
    """
    Returns a list of files that matches search term within the directory provided.
    Args:
        path (str):             directory in which to search
        search_term (str):      search term

    Returns:
        files (list of str):    list of files
    """
    files = []
    # r=root, d=directories, f = files
    for r, d, f in os.walk(path):
        for file in f:
            if search_term in file:
                files.append(os.path.join(r, file))
    return files


def bulk_down_res(incoming_resolution: str = "480p", outgoing_resolution: str = "360p"):
    files = get_file_list('egg_photos/test', '_' + incoming_resolution + '.JPG')
    for f in files:
        img, rf = image_rescale(cv2.imread(f), (480, 360))
        cv2.imwrite(f[:-8] + outgoing_resolution + f[-4:], img)


def bulk_gen_dmap():
    files = get_file_list('egg_photos/test', '_360p.JPG')
    for f in files:
        dmap = generate_density_map(f, f[:-3] + 'txt')
        np.savetxt(f[:-4]+'_dmap.txt', dmap)
