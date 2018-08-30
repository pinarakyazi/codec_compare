FROM ubuntu:16.04
WORKDIR /codec_compare

# DEPENDENCIES
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    g++ \
    make \
    patchelf \
    bzip2 \
    pkg-config \
    yasm \
    subversion \
    python \
    vim \
    exuberant-ctags \
    imagemagick \
    python-plotly

# JPEG
RUN mkdir -p /tools && \
    cd /tools && \
    wget -O jpeg.zip https://jpeg.org/downloads/jpegxt/reference1367abcd89.zip && \
    unzip jpeg.zip -d jpeg && \
    rm -f jpeg.zip && \
    cd jpeg && \
    ./configure && \
    make

# KAKADU
RUN mkdir -p /tools && \
    cd /tools && \
    wget -O kakadu.zip http://kakadusoftware.com/wp-content/uploads/2014/06/KDU7A2_Demo_Apps_for_Ubuntu-x86-64_170827.zip && \
    unzip kakadu.zip -d kakadu && \
    rm -f kakadu.zip && \
    patchelf --set-rpath '$ORIGIN/' /tools/kakadu/KDU7A2_Demo_Apps_for_Ubuntu-x86-64_170827/kdu_compress && \
    patchelf --set-rpath '$ORIGIN/' /tools/kakadu/KDU7A2_Demo_Apps_for_Ubuntu-x86-64_170827/kdu_expand && \
    patchelf --set-rpath '$ORIGIN/' /tools/kakadu/KDU7A2_Demo_Apps_for_Ubuntu-x86-64_170827/kdu_v_compress && \
    patchelf --set-rpath '$ORIGIN/' /tools/kakadu/KDU7A2_Demo_Apps_for_Ubuntu-x86-64_170827/kdu_v_expand

# WEBP
RUN mkdir -p /tools && \
    cd /tools && \
    wget -O libwebp.tar.gz https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-1.0.0-linux-x86-64.tar.gz  && \
    tar xvzf libwebp.tar.gz && \
    rm -f libwebp.tar.gz
RUN apt-get install libglu1 -y
RUN apt-get install libxi6 -y

# HEVC
RUN mkdir -p /tools && \
    cd /tools && \
    svn checkout https://hevc.hhi.fraunhofer.de/svn/svn_HEVCSoftware/tags/HM-16.18+SCM-8.7/ && \
    cd HM-16.18+SCM-8.7/build/linux && \
    make

# VMAF, FFMPEG
RUN mkdir -p /tools && \
    cd /tools && \
    wget -O vmaf.zip https://github.com/Netflix/vmaf/archive/v1.3.1.zip && \
    unzip vmaf.zip && \
    rm -f vmaf.zip && \
    cd vmaf-1.3.1 && \
    make && \
    make install && \
    cd /tools && \
    wget -O ffmpeg.tar.bz2 http://ffmpeg.org/releases/ffmpeg-3.4.1.tar.bz2 && \
    tar -vxjf ffmpeg.tar.bz2 && \
    rm ffmpeg.tar.bz2 && \
    cd ffmpeg-3.4.1 && \
    ./configure --enable-libvmaf && \
    make install

# DIFFTEST_NG
RUN mkdir -p /tools && \
    cd /tools && \
    wget -O difftest_ng-master.zip https://github.com/thorfdbg/difftest_ng/archive/master.zip  && \
    unzip difftest_ng-master.zip && \
    rm -f difftest_ng-master.zip && \
    cd difftest_ng-master && \
    ./configure && \
    make && \
    make install

# HDRTools 0.18-dev
RUN mkdir -p /tools && \
    cd /tools && \
    wget -O HDRTools-0.18-dev.tar.gz https://gitlab.com/standards/HDRTools/-/archive/0.18-dev/HDRTools-0.18-dev.tar.gz && \
    tar xvzf HDRTools-0.18-dev.tar.gz && \
    rm -f HDRTools-0.18-dev.tar.gz && \
    cd HDRTools-0.18-dev && \
    make

# TO ADD ANOTHER
# ADD /local/path/to/bin /tools/bin
# ^ This will add the file from the host machine into the container. In this case the bin is accessible at: `/tools/bin`.
