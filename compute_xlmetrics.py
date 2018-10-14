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
        if res_split[-1][m - 2] == "_":
            depth = res_split[-1][m - 1]
        else:
            depth = res_split[-1][m - 2:m]
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
    vmaf_dict["vmaf"] = vmaf_log["frames"][0]["metrics"]["vmaf"]
    vmaf_dict["vif"] = vmaf_log["frames"][0]["metrics"]["vif_scale0"]
    vmaf_dict["ssim"] = vmaf_log["frames"][0]["metrics"]["ssim"]
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

    logfile = '/tmp/stats.log'

    HDRConvert_dir = '/tools/HDRTools-0.18-dev/bin/HDRConvert'
    ppm_to_yuv_cfg = 'convert_configs/HDRConvertPPMToYCbCr444fr.cfg'

    chroma_fmt = 3

    HDRMetrics_dir = '/tools/HDRTools-0.18-dev/bin/HDRMetrics'
    HDRMetrics_config = 'convert_configs/HDRMetrics.cfg'

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
               '-p', 'Input1ColorPrimaries=4', '-p', 'Input0ColorPrimaries=4', '-p', 'Input0ColorSpace=0', '-p',
               'Input1ColorSpace=0', '>', '/tmp/statsHDRTools_SDRmetrics.json']
        subprocess.check_output(' '.join(cmd), stderr=subprocess.STDOUT, shell=True)
    except subprocess.CalledProcessError as e:
        print cmd, e.output
        raise e

    objective_dict = dict()
    with open('/tmp/statsHDRTools_SDRmetrics.json', 'r') as f:
        for line in f:
            if '000000' in line:
                metriclist = line.split()
                objective_dict["psnr-y"] = metriclist[1]
                if 'classB' not in ref_image:
                    objective_dict["psnr-avg"] = (6 * float(metriclist[1]) + float(metriclist[2]) + float(
                        metriclist[3])) / 8.0
                objective_dict["ms_ssim"] = metriclist[4]
                objective_dict["ssim"] = metriclist[7]

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
        vmaf_dict["vif"] = vmaf_log["frames"][0]["metrics"]["vif_scale0"]
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

    primary = '1'

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
               '-p', 'Input0Height=%s' % height, '-p', 'Input0ChromaFormat=%d' % chroma_fmt, '-p', 'Input0ColorSpace=1',
               '-p',
               'Input0BitDepthCmp0=%s'
               % depth, '-p', 'Input0BitDepthCmp1=%s' % depth, '-p', 'Input0BitDepthCmp2=%s' % depth, '-p',
               'Input1ColorSpace=1', '-p',
               'Input1File=%s' % dist_image, '-p', 'Input1Width=%s' % width, '-p', 'Input1Height=%s' % height, '-p',
               'Input1ChromaFormat=%d' % chroma_fmt, '-p', 'Input1BitDepthCmp0=%s' % depth, '-p',
               'Input1BitDepthCmp1=%s' % depth, '-p', 'Input1BitDepthCmp2=%s' % depth, '-p', 'LogFile=%s' % logfile,
               '-p', 'Input0ColorPrimaries=1', '-p', 'Input1ColorPrimaries=1', '-p', '-p', 'TFPSNRDistortion=1', '-p',
               'EnableTFPSNR=1', '-p', 'EnableTFMSSSIM=1',
               '>', '/tmp/statsHDRTools.json']
        subprocess.check_output(' '.join(cmd), stderr=subprocess.STDOUT, shell=True)
        print(' '.join(cmd))
    except subprocess.CalledProcessError as e:
        print cmd, e.output
        raise e

    objective_dict = dict()
    with open('/tmp/statsHDRTools.json', 'r') as f:
        for line in f:
            if '000000' in line:
                metriclist = line.split()
                objective_dict["psnr-y"] = metriclist[5]
                objective_dict["ms_ssim"] = metriclist[9]

    return objective_dict


def create_derivatives(image, classname):
    """ given a test image, create ppm and yuv derivatives
    """
    name = os.path.basename(image).split(".")[0]
    extension = os.path.splitext(image)[1]
    derivative_images = []

    yuv_dir = os.path.join('derivative_images', 'yuv420p')
    yuv_dest = os.path.join(yuv_dir, name + '.yuv')

    ppm_dir = os.path.join('derivative_images', 'ppm')
    if 'tif' in extension and 'XRAY' not in name:
        ppm_dest = os.path.join(ppm_dir, name + '.tif')
    else:
        ppm_dest = os.path.join(ppm_dir, name + '.ppm')

    width, height, depth = get_dimensions(image, classname)

    HDRTools_dir = '/tools/HDRTools-0.18-dev/bin/HDRConvert'
    ppm_to_yuv_cfg = 'convert_configs/HDRConvertPPMToYCbCr420fr.cfg'

    if 'classB' in classname:
        if not os.path.isfile(ppm_dest):
            try:
                print "\033[92m[PPM]\033[0m " + ppm_dest
                mkdir_p(ppm_dir)
                cmd = ["/tools/difftest_ng-master/difftest_ng", "--convert", ppm_dest, os.path.join('images', image),
                       "-"]
                subprocess.check_output(" ".join(cmd), stderr=subprocess.STDOUT, shell=True)
            except subprocess.CalledProcessError as e:
                print cmd, e.output
                raise e
                exit(1)
        else:
            print "\033[92m[PPM OK]\033[0m " + ppm_dest

        derivative_images.append((ppm_dest, 'ppm'))
        return derivative_images

    if 'WALTHAM' in name:
        if not os.path.isfile(ppm_dest):
            try:
                print "\033[92m[PPM]\033[0m " + ppm_dest
                mkdir_p(ppm_dir)
                cmd = ["/tools/difftest_ng-master/difftest_ng", "--convert", ppm_dest, os.path.join('images', image),
                       "-"]
                subprocess.check_output(" ".join(cmd), stderr=subprocess.STDOUT, shell=True)
            except subprocess.CalledProcessError as e:
                print cmd, e.output
                raise e
                exit(1)
        else:
            print "\033[92m[PPM OK]\033[0m " + ppm_dest

        derivative_images.append((ppm_dest, 'ppm'))

    if not os.path.isfile(yuv_dest):
        try:
            print "\033[92m[YUV420]\033[0m " + yuv_dest
            mkdir_p(yuv_dir)
            cmd = [HDRTools_dir, '-f', ppm_to_yuv_cfg, '-p', 'SourceFile=%s' % image, '-p', 'SourceWidth=%s' % width,
                   '-p', 'SourceHeight=%s' % height, '-p', 'SourceBitDepthCmp0=%s' % depth, '-p',
                   'SourceBitDepthCmp1=%s'
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


def convert_decoded(image, width, height, depth, codecname):
    name, extension = os.path.splitext(os.path.basename(image))
    HDRTools_dir = '/tools/HDRTools-0.18-dev/bin/HDRConvert'
    primary = '0'
    if 'tat' in codecname or 'webp' in codecname:  # decoded image is YCbCr4:2:0
        yuv444_dir = os.path.join('objective_images', 'YUV420_YUV444')
        yuv444_dest = os.path.join(yuv444_dir, name + '.yuv')
        config = 'convert_configs/HDRConvertYCbCr420ToYCbCr444.cfg'
    else:
        yuv444_dir = os.path.join('objective_images', 'PPM444_YUV444')
        yuv444_dest = os.path.join(yuv444_dir, name + '.yuv')
        config = 'convert_configs/HDRConvertPPMToYCbCr444fr.cfg'
    if not os.path.isfile(yuv444_dest):
        try:
            print "\033[92m[YUV444]\033[0m " + yuv444_dest
            mkdir_p(yuv444_dir)
            cmd = [HDRTools_dir, '-f', config, '-p', 'SourceFile=%s' % image, '-p',
                   'SourceWidth=%s' % width,
                   '-p', 'SourceHeight=%s' % height, '-p', 'SourceBitDepthCmp0=%s' % depth, '-p',
                   'SourceBitDepthCmp1=%s'
                   % depth, '-p', 'SourceBitDepthCmp2=%s' % depth, '-p', 'SourceColorPrimaries=%s' % primary, '-p',
                   'OutputFile=%s' % yuv444_dest, '-p', 'OutputWidth=%s' % width, '-p', 'OutputHeight=%s' % height,
                   '-p',
                   'OutputBitDepthCmp0=%s' % depth, '-p', 'OutputBitDepthCmp1=%s' % depth, '-p',
                   'OutputBitDepthCmp2=%s'
                   % depth, '-p', 'OutputColorPrimaries=%s' % primary]
            subprocess.check_output(' '.join(cmd), stderr=subprocess.STDOUT, shell=True)
            # print(' '.join(cmd))
        except subprocess.CalledProcessError as e:
            print "\033[91m[ERROR]\033[0m"
            print cmd, e.output
            #raise e
        else:
            print "\033[92m[YUV420 OK]\033[0m " + yuv444_dest

    return yuv444_dest

def main():
    """ check for Docker, check for complementary encoding and decoding scripts, check for test images.
        fire off encoding and decoding scripts, followed by metrics computations.
    """

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

    codeclist_full = set(['aom', 'deepcoder', 'deepcoder-lite', 'fuif', 'fvdo', 'hevc', 'kakadu', 'jpeg',
                    'pik', 'tat', 'xavs', 'xavs-fast', 'xavs-median', 'webp'])

    bpp_targets = set([0.06, 0.12, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00])
    for image in images:
        width, height, depth = get_dimensions(image, classname)
        name, imgfmt = os.path.splitext(image)
        imgfmt = os.path.basename(image).split(".")[-1]
        derivative_images = []
        if classname[:6] == 'classB':
            derivative_images = create_derivatives(image, classname)
        else:
            derivative_images.append((image, imgfmt))

        for derivative_image, pix_fmt in derivative_images:
            json_dir = 'metrics'
            mkdir_p(json_dir)
            json_file = os.path.join(json_dir,
                                     os.path.splitext(os.path.basename(derivative_image))[0] + "." + pix_fmt + ".json")
            # if os.path.isfile(json_file):
            #     print "\033[92m[JSON OK]\033[0m " + json_file
            #     continue
            main_dict = dict()
            derivative_image_metrics = dict()
            for codecname in codeclist_full:
                convertflag = 1
                caseflag = pix_fmt
                if (codecname == 'webp' or codecname == 'tat' or 'deepcoder' in codecname) and depth != '8':
                    continue
                if 'xavs' in codecname and depth != '8' and depth != '10':
                    continue
                if 'classE' in classname and ('tat' in codecname or 'xavs' in codecname or 'deepcoder' in codecname):
                    continue
                if codecname == 'kakadu' and classname[:6] == 'classB':
                    convertflag = 0
                    caseflag = imgfmt
                bpp_target_metrics = dict()
                for bpp_target in bpp_targets:
                    print(codecname)
                    if codecname == 'aom' and classname[:6] == 'classB':
                        # ('AERIAL2' in image or 'CATS' in image or 'XRAY' in image or 'GOLD' in image or 'TEXTURE1' in image):
                        encoded_image_name = os.path.splitext(os.path.basename(derivative_image))[
                                                 0] + '_' + str(bpp_target) + '_' + imgfmt + '.' + 'av1'
                        encoded_image = os.path.join('outputs', codecname, encoded_image_name)
                        decoded_image = os.path.join('outputs', codecname, 'decoded', encoded_image_name + '.' + imgfmt)
                        original_image = image
                    elif codecname == 'kakadu' and classname[:6] == 'classB':
                        encoded_image_name = os.path.splitext(os.path.basename(derivative_image))[
                                                 0] + '_' + str(bpp_target) + '_' + imgfmt + '.' + codecname
                        encoded_image = os.path.join('outputs', codecname, encoded_image_name)
                        decoded_image = os.path.join('outputs', codecname, 'decoded', encoded_image_name + '.' + imgfmt)
                        original_image = image
                    elif 'xavs' in codecname and classname[:6] == 'classB':
                        encoded_image_name = os.path.splitext(os.path.basename(derivative_image))[
                                                 0] + '_' + str(bpp_target) + '_' + imgfmt + '.' + codecname
                        encoded_image = os.path.join('outputs', codecname, encoded_image_name)
                        decoded_image = os.path.join('outputs', codecname, 'decoded', encoded_image_name + '.' + imgfmt)
                        original_image = image
                    elif codecname == 'fvdo' and classname[:6] == 'classB':
                        encoded_image_name = os.path.splitext(os.path.basename(derivative_image))[
                                                 0] + '_' + str(bpp_target) + '_pgm' + '.' + codecname
                        encoded_image = os.path.join('outputs', codecname, encoded_image_name)
                        decoded_image = os.path.join('outputs', codecname, 'decoded', encoded_image_name + '.pgm')
                        original_image = image
                    else:
                        if codecname == 'fuif' and 'tif' in imgfmt:
                            encoded_image_name = os.path.splitext(os.path.basename(derivative_image))[
                                                     0] + '.tif_' + str(bpp_target) + '_' + pix_fmt + '.' + codecname
                        elif codecname == 'webp' or codecname == 'tat':
                            encoded_image_name = os.path.splitext(os.path.basename(derivative_image))[
                                                     0] + '_' + str(bpp_target) + '_yuv420p.' + codecname
                        else:
                            encoded_image_name = os.path.splitext(os.path.basename(derivative_image))[
                                                    0] + '_' + str(bpp_target) + '_' + pix_fmt + '.' + codecname
                        encoded_image = os.path.join('outputs', codecname, encoded_image_name)
                        decoded_image_path = os.path.join('outputs', codecname, 'decoded')
                        decoded_image = ''
                        for decodedfile in os.listdir(decoded_image_path):
                            encoderoot = '_'.join(os.path.splitext(os.path.basename(encoded_image_name))[0].split('_')[:-1])
                            if encoderoot in decodedfile:
                                if ('tat' in codecname or 'webp' in codecname) and os.path.splitext(os.path.basename(decodedfile))[1] == '.yuv':
                                    decoded_image = os.path.join('outputs', codecname, 'decoded', decodedfile)
                                    print(decoded_image)
                                if ('tat' not in codecname or 'webp' not in codecname) and os.path.splitext(os.path.basename(decodedfile))[1] != '.yuv':
                                    decoded_image = os.path.join('outputs', codecname, 'decoded', decodedfile)
                        if 'classE' not in classname and 'classB' not in classname and os.path.isfile(decoded_image):
                            decoded_image = convert_decoded(decoded_image, width, height, depth, codecname)
                            original_image = convert_decoded(derivative_image, width, height, depth, 'reference')
                        else:
                            original_image = derivative_image

                    print('Reference:' + original_image)
                    print('Encoded:' + encoded_image)
                    print('Decoded:' + decoded_image)
                    if (os.path.isfile(original_image) and os.path.isfile(decoded_image) and os.path.isfile(encoded_image)):
                        if 'classE' in classname:
                            metrics = compute_metrics_HDR(original_image, decoded_image, encoded_image, bpp_target,
                                                          codecname, width, height, pix_fmt, depth)

                        elif 'classB' in classname:
                            metrics = compute_metrics(original_image, decoded_image, encoded_image, bpp_target, codecname,
                                                      width, height, pix_fmt)
                        else:
                            metrics = compute_metrics_SDR(original_image, decoded_image, encoded_image, bpp_target,
                                                          codecname, width,
                                                          height, imgfmt, depth)
                        measured_bpp = (os.path.getsize(encoded_image) * 1.024 * 8) / (float((int(width) * int(height))))
                        bpp_target_metrics[measured_bpp] = metrics
                    else:
                        continue
                
                derivative_image_metrics[codecname] = bpp_target_metrics
            main_dict[derivative_image] = derivative_image_metrics

            mkdir_p(json_dir)
            with open(json_file, 'w') as f:
                f.write(json.dumps(main_dict, indent=2))


if __name__ == "__main__":
    main()
