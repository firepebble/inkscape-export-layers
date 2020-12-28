#! /usr/bin/env python
import collections
import contextlib
import copy
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.append('/usr/share/inkscape/extensions')
import inkex

#import logging

Layer = collections.namedtuple('Layer', ['id', 'label', 'tag'])
Export = collections.namedtuple('Export', ['visible_layers', 'file_name'])

FIXED = '[fixed]'
EXPORT = '[export]'

PNG = 'png'
SVG = 'svg'
JPEG = 'jpeg'


class LayerExport(inkex.Effect):
    def __init__(self):
        inkex.Effect.__init__(self)
        self.arg_parser.add_argument('-o', '--output-dir',
                                     action='store',
                                     type=str,
                                     dest='output_dir',
                                     default='~/',
                                     help='Path to an output directory')
        self.arg_parser.add_argument('-f', '--file-type',
                                     action='store',
                                     type=str,
                                     choices=['png', 'svg', 'jpeg'],
                                     dest='file_type',
                                     default='svg',
                                     help='Exported file type')
        self.arg_parser.add_argument('--fit-contents',
                                     action='store',
                                     type=inkex.Boolean,
                                     dest='fit_contents',
                                     default=False,
                                     help='Fit output to content bounds')
        self.arg_parser.add_argument('--dpi',
                                     action='store',
                                     type=int,
                                     dest='dpi',
                                     default=300,
                                     help="Export DPI value")
        self.arg_parser.add_argument('--enumerate',
                                     action='store',
                                     type=inkex.Boolean,
                                     dest='enumerate',
                                     default=None,
                                     help="Export DPI value")

    def effect(self):
#        logging.warning("Looking for outputDir")
        output_dir = os.path.expanduser(self.options.output_dir)
#        logging.warning("OutputDir is: %s", output_dir)
        if not os.path.exists(os.path.join(output_dir)):
#            logging.warning("Trying to make you a directory at: %s", output_dir)
            os.makedirs(os.path.join(output_dir))

        layer_list = self.get_layer_list()
        export_list = self.get_export_list(layer_list)
#        logging.warning("Got the layer and export lists: %s and %s", layer_list, export_list)
        with _make_temp_directory() as tmp_dir:
            for export in export_list:
                svg_file = self.export_to_svg(export, tmp_dir)

                if self.options.file_type == PNG:
                    if not self.convert_svg_to_png(svg_file, output_dir):
                        break
                elif self.options.file_type == SVG:
#                    logging.warning("SVG Selected for file: %s and dir: %s", svg_file, output_dir)
                    if not self.convert_svg_to_svg(svg_file, output_dir):
#                        logging.warning("svg to svg failed")
                        break
                elif self.options.file_type == JPEG:
                    if not self.convert_png_to_jpeg(
                            self.convert_svg_to_png(svg_file, tmp_dir),
                            output_dir):
                        break

    def get_layer_list(self):
        svg_layers = self.document.xpath('//svg:g[@inkscape:groupmode="layer"]',
                                         namespaces=inkex.NSS)
#        logging.warning("Trying to get the svg layers: %s", svg_layers)
        layer_list = []
#        logging.warning("starting for loop for svg_layers")
        for layer in svg_layers:
            label_attrib_name = '{%s}label' % layer.nsmap['inkscape']
#            logging.warning("label attribute: %s", label_attrib_name)
            if label_attrib_name not in layer.attrib:
                continue

            layer_id = layer.attrib['id']
            layer_label = layer.attrib[label_attrib_name]
#            logging.warning("got layer id and label: %s and %s", layer_id, layer_label)

            if layer_label.lower().startswith(FIXED):
                layer_type = FIXED
                layer_label = layer_label[len(FIXED):].lstrip()
            elif layer_label.lower().startswith(EXPORT):
                layer_type = EXPORT
                layer_label = layer_label[len(EXPORT):].lstrip()
            else:
#                logging.warning("Found nothing to export")
                continue
#            logging.warning("finished for loop for svg_layers")
            layer_list.append(Layer(layer_id, layer_label, layer_type))
#            logging.warning("layer list is now: %s", layer_list)
        # Layers are displayed in the reversed order in Inkscape compared to SVG
        
        return list(reversed(layer_list))

    def get_export_list(self, layer_list):
        export_list = []

        for counter, layer in enumerate(layer_list):
            if layer.tag == FIXED:
                continue

            visible_layers = {
                other_layer.id for other_layer in layer_list
                if other_layer.tag == FIXED or other_layer.id == layer.id
            }

            file_name = layer.label
            if self.options.enumerate:
                file_name = '%03d_%s' % (counter + 1, file_name)

            export_list.append(Export(visible_layers, file_name))

        return export_list

    def export_to_svg(self, export, output_dir):
        """
        Export a current document to an Inkscape SVG file.
        :arg Export export: Export description.
        :arg str output_dir: Path to an output directory.
        :return Output file path.
        """
        document = copy.deepcopy(self.document)

        svg_layers = document.xpath('//svg:g[@inkscape:groupmode="layer"]',
                                    namespaces=inkex.NSS)

        for layer in svg_layers:
            if layer.attrib['id'] in export.visible_layers:
                layer.attrib['style'] = 'display:inline'
            else:
                layer.attrib['style'] = 'display:none'

        output_file = os.path.join(output_dir, export.file_name + '.svg')
        document.write(output_file)

        return output_file

    def convert_svg_to_png(self, svg_file, output_dir):
        """
        Convert an SVG file into a PNG file.
        :param str svg_file: Path an input SVG file.
        :param str output_dir: Path to an output directory.
        :return Output file path.
        """
        file_name = os.path.splitext(os.path.basename(svg_file))[0]
        output_file = os.path.join(output_dir, file_name + '.png')
        command = [
            'inkscape',
            '--export-area-drawing' if self.options.fit_contents else
            '--export-area-page',
            '--export-dpi', str(self.options.dpi),
            '--export-png', output_file.encode('utf-8'),
            svg_file.encode('utf-8')
        ]
        p = subprocess.Popen(command,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        if p.wait() != 0:
            raise Exception('Failed to convert %s to PNG' % svg_file)

        return output_file

    def convert_svg_to_svg(self, svg_file, output_dir):
        """
        Convert an [Inkscape] SVG file into a standard (plain) SVG file.
        :param str svg_file: Path an input SVG file.
        :param str output_dir: Path to an output directory.
        :return Output file path.
        """
#        logging.warning("starting svg to svg converstion")
        file_name = os.path.splitext(os.path.basename(svg_file))[0]
        output_file = os.path.join(output_dir, file_name + '.svg')
#        logging.warning("Using file: %s and output: %s", file_name, output_file)
        command = [
            'inkscape',
            '--export-area-drawing' if self.options.fit_contents else
            '--export-area-page',
            '--export-dpi', str(self.options.dpi),
            '--export-plain-svg',
            '--export-filename', output_file.encode('utf-8'),
            '--vacuum-defs',
            svg_file.encode('utf-8')
        ]
#        logging.warning("Command: %s", command)
        p = subprocess.Popen(command,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)

        p.stdout.close()
        return_code = p.wait()
        if return_code:
             raise subprocess.CalledProcessError(return_code, command)
#             logging.warning("issues return code: %s", return_code)

#        if p.wait() != 0:
#            raise Exception('Failed to convert %s to PNG' % svg_file)
#        logging.warning("returning output file: %s", output_file)
        return output_file

    @staticmethod
    def convert_png_to_jpeg(png_file, output_dir):
        """
        Convert a PNG file into a JPEG file.
        :param str png_file: Path an input PNG file.
        :param str output_dir: Path to an output directory.
        :return Output file path.
        """
        if png_file is None:
            return None

        file_name = os.path.splitext(os.path.basename(png_file))[0]
        output_file = os.path.join(output_dir, file_name + '.jpeg')
        command = ['convert', png_file, output_file]
        p = subprocess.Popen(command,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        if p.wait() != 0:
            raise Exception('Is ImageMagick installed?\n'
                            'Failed to convert %s to JPEG' % png_file)

        return output_file


@contextlib.contextmanager
def _make_temp_directory():
    temp_dir = tempfile.mkdtemp(prefix='tmp-inkscape')
    try:
        yield temp_dir
    except Exception as e:
#        logging.warning(e)
        inkex.errormsg(str(e))
    finally:
#        logging.warning("Removing temp dir: %s", temp_dir)
        shutil.rmtree(temp_dir)


if __name__ == '__main__':
#    logging.warning('Started')
    try:
#        logging.warning('trying')
        LayerExport().run(output=False)
    except Exception as e:
#        logging.warning(e)
        inkex.errormsg(str(e))
sys.exit(0)
