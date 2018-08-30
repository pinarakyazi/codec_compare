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

def compute_vmaf(ref_image, dist_image, width, height, pix_fmt):
    """ given a pair of reference and distored images:
        use the ffmpeg libvmaf filter to compute vmaf, vif, ssim, and ms_ssim.
    """

    log_path = '/tmp/stats.json'
    cmd = ['ffmpeg', '-s:v', '%s,%s' % (width, height), '-i', dist_image,
            '-s:v', '%s,%s' % (width, height), '-i', ref_image,
            '-lavfi', 'libvmaf=ssim=true:ms_ssim=true:log_fmt=json:log_path=' + log_path,
            '-f', 'null', '-'
          ]

    try:
        print "\033[92m[VMAF]\033[0m " + dist_image
        subprocess.check_output(" ".join(cmd), stderr=subprocess.STDOUT, shell=True)
    except subprocess.CalledProcessError as e:
        print "\033[91m[ERROR]\033[0m " + " ".join(cmd) + "\n" + e.output

    vmaf_log = json.load(open(log_path))

    vmaf_dict = dict()
    vmaf_dict["vmaf"]    = vmaf_log["frames"][0]["metrics"]["vmaf"]
    vmaf_dict["vif"]     = vmaf_log["frames"][0]["metrics"]["vif_scale0"]
    vmaf_dict["ssim"]    = vmaf_log["frames"][0]["metrics"]["ssim"]
    vmaf_dict["ms_ssim"] = vmaf_log["frames"][0]["metrics"]["ms_ssim"]
    return vmaf_dict

def compute_psnr(ref_image, dist_image, width, height):
    """ given a pair of reference and distorted images:
        use the ffmpeg psnr filter to compute psnr and mse for each channel.
    """

    log_path = '/tmp/stats.log'
    cmd = ['ffmpeg', '-s:v', '%s,%s' % (width, height), '-i', dist_image,
            '-s:v', '%s,%s' % (width, height), '-i', ref_image,
            '-lavfi', 'psnr=stats_file=' + log_path,
            '-f', 'null', '-'
          ]

    try:
        print "\033[92m[PSNR]\033[0m " + dist_image
        subprocess.check_output(" ".join(cmd), stderr=subprocess.STDOUT, shell=True)
    except subprocess.CalledProcessError as e:
        print "\033[91m[ERROR]\033[0m " + e.output

    psnr_dict = dict()
    psnr_log = open(log_path).read()
    for stat in psnr_log.rstrip().split(" "):
        key, value = stat.split(":")
        if key is not "n" and not 'mse' in key:
            psnr_dict[key] = float(value)
    return psnr_dict

def compute_metrics(ref_image, dist_image, encoded_image, bpp_target, codec, width, height, pix_fmt):
    """ given a pair of reference and distorted images:
        call vmaf and psnr functions, dump results to a json file.
        """
    
    vmaf = compute_vmaf(ref_image, dist_image, width, height, pix_fmt)
    psnr = compute_psnr(ref_image, dist_image, width, height)
    stats = vmaf.copy()
    stats.update(psnr)
    return stats

def compute_metrics_SDR(ref_image, dist_image, encoded_image, bpp_target, codec, width, height, pix_fmt, depth):
    """ given a pair of reference and distorted images:
        call vmaf and psnr functions, dump results to a json file.
    """
    refname, ref_pix_fmt = os.path.basename(ref_image).split(".")
    dist_pix_fmt = os.path.basename(dist_image).split(".")[-1]
    
    if 'classE' in ref_image:
        primary = '1'
    else:
        primary = '0'

    logfile = '/tmp/stats.log'

    HDRConvert_dir = '/tools/HDRTools-0.18-dev/bin/HDRConvert'
    ppm_to_yuv_cfg = 'convert_configs/HDRConvertPPMToYCbCr444fr.cfg'


    if 'yuv' in pix_fmt and not 'jpeg' in dist_image:
        chroma_fmt = 1
    else:
        chroma_fmt = 3

    if 'HOTEL' in refname:
        chroma_fmt = 0
    
    HDRMetrics_dir = '/tools/HDRTools-0.18-dev/bin/HDRMetrics'
    HDRMetrics_config =  'convert_configs/HDRMetrics.cfg'

    try:
        cmd = [HDRMetrics_dir, '-f', HDRMetrics_config, '-p', 'Input0File=%s' % ref_image, '-p',
               'Input0Width=%s' % width,
               '-p', 'Input0Height=%s' % height, '-p', 'Input0ChromaFormat=%d' % chroma_fmt, '-p',
               'Input0BitDepthCmp0=%s'
               % depth, '-p', 'Input0BitDepthCmp1=%s' % depth, '-p', 'Input0BitDepthCmp2=%s' % depth, '-p',
               'Input1File=%s' % dist_image, '-p', 'Input1Width=%s' % width, '-p', 'Input1Height=%s' % height, '-p',
               'Input1ChromaFormat=%d' % chroma_fmt, '-p', 'Input1BitDepthCmp0=%s' % depth, '-p',
               'Input1BitDepthCmp1=%s' % depth, '-p', 'Input1BitDepthCmp2=%s' % depth, '-p', 'LogFile=%s' % logfile,
               '-p', 'TFPSNRDistortion=0', '-p', 'EnablePSNR=1', '-p', 'EnableSSIM=1', '-p', 'EnableMSSSIM=1',
               '>', '/tmp/statsHDRTools.json']
        subprocess.check_output(' '.join(cmd), stderr=subprocess.STDOUT, shell=True)
    except subprocess.CalledProcessError as e:
        print cmd, e.output
        raise e

    objective_dict = dict()
    with open('/tmp/statsHDRTools.json', 'r') as f:
        for line in f:
            if '000000' in line:
                metriclist = line.split()
                objective_dict["psnr-y"]   = metriclist[1]
                if 'classB' not in ref_image:
                    objective_dict["psnr-avg"] = (6*float(metriclist[1])+float(metriclist[2])+float(metriclist[3]))/8.0
                objective_dict["ms_ssim"]  = metriclist[4]
                objective_dict["ssim"]     = metriclist[7]

    if depth == '8':
        log_path = '/tmp/stats.json'
        cmd = ['ffmpeg', '-s:v', '%s,%s' % (width, height), '-i', dist_image,
               '-s:v', '%s,%s' % (width, height), '-i', ref_image,
               '-lavfi', 'libvmaf=log_fmt=json:log_path=' + log_path,
               '-f', 'null', '-'
               ]
        try:
            print "\033[92m[VMAF]\033[0m " + dist_image
            subprocess.check_output(" ".join(cmd), stderr=subprocess.STDOUT, shell=True)
        except subprocess.CalledProcessError as e:
            print "\033[91m[ERROR]\033[0m " + " ".join(cmd) + "\n" + e.output

        vmaf_log = json.load(open(log_path))

        vmaf_dict = dict()
        vmaf_dict["vmaf"] = vmaf_log["frames"][0]["metrics"]["vmaf"]
        vmaf_dict["vif"]  = vmaf_log["frames"][0]["metrics"]["vif_scale0"]
        stats = vmaf_dict.copy()
        stats.update(objective_dict)

    else:
        stats = objective_dict

    return stats

def compute_metrics_HDR(ref_image, dist_image, encoded_image, bpp_target, codec, width, height, pix_fmt, depth):
    """ given a pair of reference and distorted images:
        call vmaf and psnr functions, dump results to a json file.
    """
    ref_pix_fmt = os.path.basename(ref_image).split(".")[-1]
    dist_pix_fmt = os.path.basename(dist_image).split(".")[-1]
    HDRConvert_dir = '/tools/HDRTools-0.18-dev/bin/HDRConvert'
    ppm_to_exr_cfg = 'convert_configs/HDRConvertPPMToEXR.cfg'
    yuv_to_exr_cfg = 'convert_configs/HDRConvertYCbCrToBT2020EXR.cfg'

    logfile = '/tmp/stats.log'

    primary = '0'

    if dist_pix_fmt == 'ppm':
        exr_dir = os.path.join('objective_images', 'PPM_EXR')
        exr_dest = os.path.join(exr_dir, os.path.basename(dist_image) + '.exr')
        if not os.path.isfile(exr_dest):
            print "\033[92m[EXR]\033[0m " + exr_dest
            mkdir_p(exr_dir)
            try:
                cmd = [HDRConvert_dir, '-f', ppm_to_exr_cfg, '-p', 'SourceFile=%s' % dist_image,
                       '-p',
                       'SourceWidth=%s' % width,
                       '-p', 'SourceHeight=%s' % height, '-p', 'SourceBitDepthCmp0=%s' % depth, '-p',
                       'SourceBitDepthCmp1=%s'
                       % depth, '-p', 'SourceBitDepthCmp2=%s' % depth, '-p', 'SourceColorPrimaries=%s' % primary, '-p',
                       'OutputFile=%s' % exr_dest, '-p', 'OutputWidth=%s' % width, '-p', 'OutputHeight=%s' % height,
                       '-p',
                       'OutputBitDepthCmp0=%s' % depth, '-p', 'OutputBitDepthCmp1=%s' % depth, '-p',
                       'OutputBitDepthCmp2=%s'
                       % depth, '-p', 'OutputColorPrimaries=%s' % primary]
                subprocess.check_output(' '.join(cmd), stderr=subprocess.STDOUT, shell=True)
            except subprocess.CalledProcessError as e:
                print cmd, e.output
                raise e
        else:
            print "\033[92m[EXR OK]\033[0m " + exr_dest

        dist_image = exr_dest
        chroma_fmt = 3

    if ref_pix_fmt == 'ppm':
        exr_dir = os.path.join('objective_images', 'PPM_EXR')
        exr_dest = os.path.join(exr_dir, os.path.basename(ref_image) + '.exr')
        if not os.path.isfile(exr_dest):
            print "\033[92m[EXR]\033[0m " + exr_dest
            mkdir_p(exr_dir)
            try:
                cmd = [HDRConvert_dir, '-f', ppm_to_exr_cfg, '-p', 'SourceFile=%s' % ref_image,
                       '-p',
                       'SourceWidth=%s' % width,
                       '-p', 'SourceHeight=%s' % height, '-p', 'SourceBitDepthCmp0=%s' % depth, '-p',
                       'SourceBitDepthCmp1=%s'
                       % depth, '-p', 'SourceBitDepthCmp2=%s' % depth, '-p', 'SourceColorPrimaries=%s' % primary, '-p',
                       'OutputFile=%s' % exr_dest, '-p', 'OutputWidth=%s' % width, '-p', 'OutputHeight=%s' % height,
                       '-p',
                       'OutputBitDepthCmp0=%s' % depth, '-p', 'OutputBitDepthCmp1=%s' % depth, '-p',
                       'OutputBitDepthCmp2=%s'
                       % depth, '-p', 'OutputColorPrimaries=%s' % primary]
                subprocess.check_output(' '.join(cmd), stderr=subprocess.STDOUT, shell=True)
            except subprocess.CalledProcessError as e:
                print cmd, e.output
                raise e
        else:
            print "\033[92m[EXR OK]\033[0m " + exr_dest
        
        ref_image = exr_dest
        chroma_fmt = 3

    if dist_pix_fmt == 'yuv':
        exr_dir = os.path.join('objective_images', 'YUV_EXR')
        exr_dest = os.path.join(exr_dir, os.path.basename(dist_image) + '.exr')
        if not os.path.isfile(exr_dest):
            print "\033[92m[EXR]\033[0m " + exr_dest
            mkdir_p(exr_dir)
            try:
                cmd = [HDRConvert_dir, '-f', yuv_to_exr_cfg, '-p', 'SourceFile=%s' % dist_image,
                       '-p',
                       'SourceWidth=%s' % width,
                       '-p', 'SourceHeight=%s' % height, '-p', 'SourceBitDepthCmp0=%s' % depth, '-p',
                       'SourceBitDepthCmp1=%s'
                       % depth, '-p', 'SourceBitDepthCmp2=%s' % depth, '-p', 'SourceColorPrimaries=%s' % primary, '-p',
                       'OutputFile=%s' % exr_dest, '-p', 'OutputWidth=%s' % width, '-p', 'OutputHeight=%s' % height,
                       '-p',
                       'OutputBitDepthCmp0=%s' % depth, '-p', 'OutputBitDepthCmp1=%s' % depth, '-p',
                       'OutputBitDepthCmp2=%s'
                       % depth, '-p', 'OutputColorPrimaries=%s' % primary]
                subprocess.check_output(' '.join(cmd), stderr=subprocess.STDOUT, shell=True)
            except subprocess.CalledProcessError as e:
                print cmd, e.output
                raise e
        else:
            print "\033[92m[EXR OK]\033[0m " + exr_dest

        dist_image = exr_dest
        chroma_fmt = 3

    if dist_pix_fmt == 'yuv':
        exr_dir = os.path.join('objective_images', 'YUV_EXR')
        exr_dest = os.path.join(exr_dir, os.path.basename(ref_image) + '.exr')
        if not os.path.isfile(exr_dest):
            print "\033[92m[EXR]\033[0m " + exr_dest
            mkdir_p(exr_dir)
            try:
                cmd = [HDRConvert_dir, '-f', yuv_to_exr_cfg, '-p', 'SourceFile=%s' % ref_image,
                       '-p',
                       'SourceWidth=%s' % width,
                       '-p', 'SourceHeight=%s' % height, '-p', 'SourceBitDepthCmp0=%s' % depth, '-p',
                       'SourceBitDepthCmp1=%s'
                       % depth, '-p', 'SourceBitDepthCmp2=%s' % depth, '-p', 'SourceColorPrimaries=%s' % primary, '-p',
                       'OutputFile=%s' % exr_dest, '-p', 'OutputWidth=%s' % width, '-p', 'OutputHeight=%s' % height,
                       '-p',
                       'OutputBitDepthCmp0=%s' % depth, '-p', 'OutputBitDepthCmp1=%s' % depth, '-p',
                       'OutputBitDepthCmp2=%s'
                       % depth, '-p', 'OutputColorPrimaries=%s' % primary]
                subprocess.check_output(' '.join(cmd), stderr=subprocess.STDOUT, shell=True)
            except subprocess.CalledProcessError as e:
                print cmd, e.output
                raise e
        else:
            print "\033[92m[EXR OK]\033[0m " + exr_dest
        
        ref_image = exr_dest
        chroma_fmt = 3

    HDRMetrics_dir = '/tools/HDRTools-0.18-dev/bin/HDRMetrics'
    HDRMetrics_config = HDRMetrics_dir + '/HDRMetrics_config'

    try:
        cmd = [HDRMetrics_dir, '-f', HDRMetrics_config, '-p', 'Input0File=%s' % ref_image, '-p',
               'Input0Width=%s' % width,
               '-p', 'Input0Height=%s' % height, '-p', 'Input0ChromaFormat=%d' % chroma_fmt, '-p', 'Input0ColorSpace=1', '-p',
               'Input0BitDepthCmp0=%s'
               % depth, '-p', 'Input0BitDepthCmp1=%s' % depth, '-p', 'Input0BitDepthCmp2=%s' % depth, '-p', 'Input1ColorSpace=1', '-p',
               'Input1File=%s' % dist_image, '-p', 'Input1Width=%s' % width, '-p', 'Input1Height=%s' % height, '-p',
               'Input1ChromaFormat=%d' % chroma_fmt, '-p', 'Input1BitDepthCmp0=%s' % depth, '-p',
               'Input1BitDepthCmp1=%s' % depth, '-p', 'Input1BitDepthCmp2=%s' % depth, '-p', 'LogFile=%s' % logfile,
               '-p', 'TFPSNRDistortion=1', '-p', 'EnableTFPSNR=1', '-p', 'EnableTFMSSSIM=1',
               '>', '/tmp/statsHDRTools.json']
        subprocess.check_output(' '.join(cmd), stderr=subprocess.STDOUT, shell=True)
    except subprocess.CalledProcessError as e:
        print cmd, e.output
        raise e

    objective_dict = dict()
    with open('/tmp/statsHDRTools.json', 'r') as f:
        for line in f:
            if '000000' in line:
                metriclist = line.split()
                objective_dict["psnr-y"]   = metriclist[5]
                objective_dict["ms_ssim"]  = metriclist[9]

    return objective_dict

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
            json_dir = 'metrics'
            json_file = os.path.join(json_dir, os.path.splitext(os.path.basename(derivative_image))[0] + "." + pix_fmt + ".json")
            # if os.path.isfile(json_file):
            #     print "\033[92m[JSON OK]\033[0m " + json_file
            #     continue
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
                    if 'classE' in classname:
                        if codecname == 'jpeg':
                            metrics = compute_metrics_HDR(image, decoded_image, encoded_image, bpp_target, codec, width, height, pix_fmt, depth)
                        else:
                            metrics = compute_metrics_HDR(derivative_image, decoded_image, encoded_image, bpp_target, codec, width, height, pix_fmt, depth)
                    elif 'classB' in classname:
                        metrics = compute_metrics(derivative_image, decoded_image, encoded_image, bpp_target, codec, width, height, pix_fmt)
                    else:
                        if convertflag:
                            if codecname == 'webp':
                                metrics = compute_metrics_SDR(derivative_image, decoded_image, encoded_image, bpp_target, codec, width, height, pix_fmt, depth)
                            elif codecname == 'jpeg':
                                if 'classB' in classname:
                                    metrics = compute_metrics_SDR(derivative_image, decoded_image, encoded_image, bpp_target, codec, width, height, pix_fmt, depth)
                                else:
                                    metrics = compute_metrics_SDR(image, decoded_image, encoded_image, bpp_target, codec, width, height, pix_fmt, depth)
                            else:
                                metrics = compute_metrics_SDR(derivative_image, decoded_image, encoded_image, bpp_target, codec, width, height, pix_fmt, depth)
                        else:
                            metrics = compute_metrics_SDR(image, decoded_image, encoded_image, bpp_target, codec, width, height, imgfmt, depth)
                    measured_bpp = (os.path.getsize(encoded_image) * int(depth)) / (float((int(width) * int(height))))
                    bpp_target_metrics[measured_bpp] = metrics

                derivative_image_metrics[os.path.splitext(codec)[0]] = bpp_target_metrics
            main_dict[derivative_image] = derivative_image_metrics

            mkdir_p(json_dir)
            with open(json_file, 'w') as f:
                f.write(json.dumps(main_dict, indent=2))

if __name__ == "__main__":
    main()
