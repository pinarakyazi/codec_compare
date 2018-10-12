#!/usr/bin/env python
import errno
import os
import sys
import subprocess
import json
import argparse

def mkdir_p(path):
    """ mkdir -p
    """
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

def listdir_full_path(directory):
   """ like os.listdir(), but returns full paths
   """
   for f in os.listdir(directory):
       if not os.path.isdir(f):
           yield os.path.abspath(os.path.join(directory, f))

def get_dimensions(image, classname):
    """ given a source image, return dimensions
    """
    start, ext = os.path.splitext(image)
    if ext == '.yuv':
        bitdepth = "8"
        res_split = start.split('x')
        width_split = res_split[0].split('_')
        width = width_split[-1]
        height_split = res_split[-1].split('_')
        m = res_split[-1].find("bit")
        if res_split[-1][m-2] == "_":
            depth = res_split[-1][m-1]
        else:
            depth = res_split[-1][m-2:m]
        height = height_split[0]
    elif classname == "classE_exr":
        size = os.path.basename(image).split('_')[2]
        try:
            dimension_cmd = ["identify", '-size', size, '-format', '%w,%h,%z', image]
            width, height, depth = subprocess.check_output(dimension_cmd).split(",")
        except subprocess.CalledProcessError as e:
            print dimension_cmd, e.output
    else:
        try:
            dimension_cmd = ["identify", '-format', '%w,%h,%z', image]
            width, height, depth = subprocess.check_output(dimension_cmd).split(",")
        except subprocess.CalledProcessError as e:
            print dimension_cmd, e.output
    return width, height, depth

def encode(encoder, bpp_target, image, width, height, pix_fmt, depth):
    """ given a encoding script and a test image:
        encode image for each bpp target and place it in the ./output directory
    """
    encoder_name = os.path.splitext(encoder)[0]
    output_dir = os.path.join('./output/' + encoder_name)
    mkdir_p(output_dir)
    image_name = os.path.splitext(os.path.basename(image))[0]
    image_out = os.path.join(output_dir, image_name + '_' + str(bpp_target) + '_' + pix_fmt + '.' + encoder_name)

    if os.path.isfile(image_out):
        print "\033[92m[ENCODE OK]\033[0m " + image_out
        return image_out
    encode_script = os.path.join('./encode/', encoder)
    cmd = [encode_script, image, image_out, str(bpp_target), width, height, pix_fmt, depth]
    try:
        print "\033[92m[ENCODING]\033[0m " + " ".join(cmd)
        subprocess.check_output(" ".join(cmd), stderr=subprocess.STDOUT, shell=True)
    except subprocess.CalledProcessError as e:
        print "\033[91m[ERROR]\033[0m " + e.output
        if os.path.isfile(image_out):
            os.remove(image_out)
        return
    if os.path.getsize(image_out) == 0:
        print "\033[91m[ERROR]\033[0m empty image: `" + image_out + "`, removing."
        print output
        os.remove(image_out)
        return
    else:
        return image_out

def decode(decoder, encoded_image, width, height, pix_fmt, depth):
    """ given a decoding script and a set of encoded images
        decode each image and place it in the ./output directory.
    """
    decoder_name = os.path.splitext(decoder)[0]
    output_dir = os.path.join('./output/', decoder_name, 'decoded')
    mkdir_p(output_dir)

    decode_script = os.path.join('./decode/', decoder)
    if pix_fmt == "ppm":
        ext_name = '.ppm'
    elif pix_fmt == "yuv420p":
        ext_name = '.yuv'
    elif pix_fmt == "pfm":
        ext_name = '.pfm'
    elif pix_fmt == 'pgm':
        ext_name = '.pgm'
    elif pix_fmt == 'tif':
        ext_name = '.tif'
    if 'webp' in decoder and ext_name == '.yuv':
        ext_name = '.yuv'
    decoded_image = os.path.join(output_dir, os.path.basename(encoded_image) + ext_name)
    if os.path.isfile(decoded_image):
        print "\033[92m[DECODE OK]\033[0m " + decoded_image
        return decoded_image
    cmd = [decode_script, encoded_image, decoded_image, width, height, pix_fmt, depth]
    try:
        print "\033[92m[DECODING]\033[0m " + " ".join(cmd)
        subprocess.check_output(" ".join(cmd), stderr=subprocess.STDOUT, shell=True)
    except subprocess.CalledProcessError as e:
        print "\033[91m[ERROR]\033[0m " + e.output
        if os.path.isfile(decoded_image):
            os.remove(decoded_image)
        return
    if os.path.getsize(decoded_image) == 0:
        print "\033[91m[ERROR]\033[0m empty image: `" + image_out + "`, removing."
        print output
        os.remove(decoded_image)
    else:
        return decoded_image

def create_derivatives(image, classname):
    """ given a test image, create ppm and yuv derivatives
    """
    name = os.path.basename(image).split(".")[0]
    derivative_images = []

    yuv_dir = os.path.join('derivative_images', 'yuv420p')
    yuv_dest = os.path.join(yuv_dir, name + '.yuv')
    
    ppm_dir = os.path.join('derivative_images', 'ppm')
    ppm_dest = os.path.join(ppm_dir, name + '.ppm')
    
    width, height, depth = get_dimensions(image, classname)

    HDRTools_dir = '/tools/HDRTools-0.18-dev/bin/HDRConvert'
    ppm_to_yuv_cfg = 'convert_configs/HDRConvertPPMToYCbCr420fr.cfg'

    if classname == 'classE':
        primary = '1'
    else:
        primary = '0'
    
    if 'classB' in classname:
        if not os.path.isfile(ppm_dest):
            try:
                print "\033[92m[PPM]\033[0m " + ppm_dest
                mkdir_p(ppm_dir)
                cmd = ["/tools/difftest_ng-master/difftest_ng", "--convert", ppm_dest, os.path.join('images', image), "-"]
                subprocess.check_output(" ".join(cmd), stderr=subprocess.STDOUT, shell=True)
            except subprocess.CalledProcessError as e:
                print cmd, e.output
                raise e
                exit(1)
        else:
            print "\033[92m[PPM OK]\033[0m " + ppm_dest

        derivative_images.append((ppm_dest, 'ppm'))
        return derivative_images
    
    if not os.path.isfile(yuv_dest):
        try:
            print "\033[92m[YUV420]\033[0m " + yuv_dest
            mkdir_p(yuv_dir)
            cmd = [HDRTools_dir, '-f', ppm_to_yuv_cfg, '-p', 'SourceFile=%s' % image, '-p', 'SourceWidth=%s' % width,
                   '-p', 'SourceHeight=%s' % height, '-p', 'SourceBitDepthCmp0=%s' % depth, '-p', 'SourceBitDepthCmp1=%s'
                   % depth, '-p', 'SourceBitDepthCmp2=%s' % depth, '-p', 'SourceColorPrimaries=%s' % primary, '-p',
                   'OutputFile=%s' % yuv_dest, '-p', 'OutputWidth=%s' % width, '-p', 'OutputHeight=%s' % height, '-p',
                   'OutputBitDepthCmp0=%s' % depth, '-p', 'OutputBitDepthCmp1=%s' % depth, '-p', 'OutputBitDepthCmp2=%s'
                   % depth, '-p', 'OutputColorPrimaries=%s' % primary]
            subprocess.check_output(' '.join(cmd), stderr=subprocess.STDOUT, shell=True)
        except subprocess.CalledProcessError as e:
            print cmd, e.output
            raise e
    else:
        print "\033[92m[YUV420 OK]\033[0m " + yuv_dest

    derivative_images.append((yuv_dest, 'yuv420p'))

    if not os.path.isfile(ppm_dest):
        try:
            mkdir_p(ppm_dir)
            cmd = ['cp', image, ppm_dest]
            subprocess.check_output(' '.join(cmd), stderr=subprocess.STDOUT, shell=True)
        except subprocess.CalledProcessError as e:
            print cmd, e.output
            raise e

    return derivative_images

def main():
    """ check for Docker, check for complementary encoding and decoding scripts, check for test images.
        fire off encoding and decoding scripts, followed by metrics computations.
    """
    error = False
    if not os.path.isfile('/.dockerenv'):
        print "\033[91m[ERROR]\033[0m" + " Docker is not detected. Run this script inside a container."
        error = True
    if not os.path.isdir('encode'):
        print "\033[91m[ERROR]\033[0m" + " No encode scripts directory `./encode`."
        error = True
    if not os.path.isdir('decode'):
        print "\033[91m[ERROR]\033[0m" + " No decode scripts directory `./decode`."
        error = True
    if not os.path.isdir('images'):
        print "\033[91m[ERROR]\033[0m" + " No source images directory `./images`."
        error = True
    if error:
        sys.exit(1)

    parser = argparse.ArgumentParser(description='codec_compare')
    parser.add_argument('path', metavar='DIR',
                        help='path to images folder')
    args = parser.parse_args()
    classpath = args.path
    classname = classpath.split('/')[1]

    images = set(listdir_full_path(classpath))
    if len(images) <= 0:
        print "\033[91m[ERROR]\033[0m" + " no source files in ./images."
        sys.exit(1)

    encoders = set(os.listdir('encode'))
    decoders = set(os.listdir('decode'))
    if encoders - decoders:
        print "\033[91m[ERROR]\033[0m" + " encode scripts without decode scripts:"
        for x in encoders - decoders: print "  - " + x
        error = True
    if decoders - encoders:
        print "\033[91m[ERROR]\033[0m" + " decode scripts without encode scripts:"
        for x in decoders - encoders: print "  - " + x
        error = True
    if error:
        sys.exit(1)

    bpp_targets = set([0.06, 0.12, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00])

    for image in images:
        width, height, depth = get_dimensions(image, classname)
        name, imgfmt = os.path.splitext(image)
        imgfmt = os.path.basename(image).split(".")[-1]

        if classname[:6] == 'classB':
            derivative_images = create_derivatives(image, classname)
        else:
            derivative_images = create_derivatives(image, classname)
            derivative_images.append((image, imgfmt))

        for derivative_image, pix_fmt in derivative_images:
            main_dict = dict()
            derivative_image_metrics = dict()
            for codec in encoders | decoders:
                codecname = os.path.splitext(codec)[0]
                convertflag = 1
                caseflag = pix_fmt
                if codecname == 'webp' and pix_fmt != 'yuv420p':
                    continue
                if codecname == 'webp' and depth != '8':
                    continue
                if codecname == 'kakadu' and classname[:6] == 'classB':
                    convertflag = 0
                    caseflag = imgfmt
                bpp_target_metrics = dict()
                for bpp_target in bpp_targets:
                    if convertflag:
                        encoded_image = encode(codec, bpp_target, derivative_image, width, height, pix_fmt, depth)
                    else:
                        encoded_image = encode(codec, bpp_target, image, width, height, caseflag, depth)
                    if encoded_image is None:
                        continue
                    if convertflag:
                        if 'jpeg' in codec and 'yuv' in pix_fmt:
                            decoded_image = decode(codec, encoded_image, width, height, 'ppm', depth)
                        else:
                            decoded_image = decode(codec, encoded_image, width, height, pix_fmt, depth)
                    else:
                        decoded_image = decode(codec, encoded_image, width, height, caseflag, depth)

if __name__ == "__main__":
    main()
