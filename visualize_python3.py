#!/usr/bin/env python

import os
import sys
import json
import plotly
import plotly.plotly as py
import plotly.graph_objs as go
from plotly import tools
from collections import defaultdict

def make_plots(metric_dict, file_in, src_img):
    
    numcodecs = 14
    codec_colors = {'P07': '#1f77b4', 'P01': '#ff7f0e', 'P06': '#2ca02c', 'P02': '#d62728', 'HEVC': '#9467bd', 'JPEGXT': '#8c564b',
        'JPEG2000': '#e377c2', 'P03': '#7f7f7f', 'P05': '#bcbd22', 'P04': '#17becf', 'WebP': '#aec7e8', 'P08': '#ff9896', 'P09': '#393b79', 'P10': '#e7ba52'}
    for metric in metric_dict:
        traces = []
        colorcnt=0
        for codec in metric_dict[metric]:
            codec_name = codec[0]
            data       = codec[1]

            x_axis = []
            y_axis = []
            for v in data:
                x_axis.append(v[0])
                y_axis.append(v[1])

            trace = go.Scatter(
                x = x_axis,
                y = y_axis,
                mode = 'lines+markers',
                name = codec_name,
                line = dict(color=codec_colors[codec_name])
            )
            traces.append(trace)
            colorcnt += 1

        layout = go.Layout(
            title= os.path.basename(src_img) + '(%s)' % (metric.upper()),
            xaxis=dict( title='BPP',
                titlefont=dict(
                    size=18,
                    color='#7f7f7f'
                )
            ),
            yaxis=dict(
                title=metric.upper(),
                titlefont=dict(
                    size=18,
                    color='#7f7f7f'
                )
            )
        )

        fig = go.Figure(data=traces, layout=layout)
        plotly.offline.plot(fig, filename=file_in + "." + metric + ".html", auto_open=False)

def main(args):
    for arg in args[1:]:
        if not arg.endswith('.json'):
            print(arg + ' is not a json file')
            continue

        file_in = arg
        print('plotting ' + arg)

        data    = json.load(open(file_in))
        src_img = list(data.keys())[0]
        codecs  = data[src_img].keys()

        codec_dict = defaultdict(list)
        for codec in codecs:
            metric_dict = defaultdict(list)
            bpps = list(data[src_img][codec].keys())
            bpps.sort()
            for bpp in bpps:
                metrics = data[src_img][codec][bpp] 
                for k, v in metrics.items():
                    metric_dict[k].append((bpp, v)) 
            codec_dict[codec].append(metric_dict)

        metric_dict = defaultdict(list)
        for codec in codec_dict:
            for key in codec_dict[codec]:
                for metric in key:
                    metric_dict[metric].append((codec, key[metric]))

        make_plots(metric_dict, file_in, src_img)

if __name__ == '__main__':
    main(sys.argv)
