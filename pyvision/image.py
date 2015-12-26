'''
Created on Dec 18, 2015
@author: Stephen O'Hara

This module defines the pyvision image class, which wraps
the image data (array) in a class with convenient methods.

One very useful aspect of the image class is that annotations
(such as bounding boxes that might be drawn around detection regions)
are kept on a separate layer, as opposed to drawing directly
onto the image array itself.
'''
# The following prevents a bunch of pylint no-member errors
# with the cv2 module.
# pylint: disable=E1101

import cv2
import numpy as np

try:
    import matplotlib.pyplot as plot
except ImportError:
    print("Error importing matplotlib.")
    print("Matplotlib integration will not work")

try:
    import shapely.geometry as sg
except ImportError:
    print("Error importing shapely.")
    print("Shapely is required for annotating shapes (polygons) on images.")

class Image(object):
    '''
    A pyvision3 Image object contains the image data, an
    annotations layer, and many convenient methods.
    Supports 1 channel and 3 channel images.
    '''

    def __init__(self, source, *args, desc="Pyvision Image", **kwargs):
        '''
        The constructor wraps a cv2.imread(...) function,
        passing in the args and kwargs appropriately, and
        then allocating data for the annotations layer.

        Parameters
        ----------
        desc: string
            Provide a short description of this image, that will be used
            by default in window titles and other functions
        source: string, file object, or cv2 image array
            If string, this is the full path to the image file to load.
            If file object, this is an open file handle from which to load
            the image.
            If ndarray, then we assume this is a cv2 image array which we will
            just wrap.
        args: variable
            Other args will be passed through to cv2.imread, the first arg
            should be the image source, like a file name. See the cv2 docs
            on imread for more details.
        kwargs: variable
            Keyword args will be passed through to cv2.imread

        Examples
        --------
        #loading from files
        img = pv3.Image('mypic.jpg')
        img2 = pv3.Image('mypic.jpg', cv2.IMREAD_GRAYSCALE)
        
        #loading from a file handle...this example is silly, but
        # this capability is good for example when loading from a file streamed
        # over a network connection, or S3, etc.
        with open('somepath/somefile.png', 'rb') as infile:
            img3 = pv3.Image(infile)
        
        #Wrapping of a numpy/cv2 ndarray
        img4 = pv3.Image( np.zeros( (480,640), dtype='uint8' ) )
        '''
        self.desc = desc
        if isinstance(source, np.ndarray):
            self.data = source
        elif type(source) == str:
            self.data = cv2.imread(source, *args, **kwargs)
        else:
            # assume a file object
            buf = source.read()
            x = np.fromstring(buf, dtype='uint8')
            self.data = cv2.imdecode(x, cv2.IMREAD_UNCHANGED)

        self.height, self.width = self.data.shape[0:2]
        self.nchannels = self.data.shape[2] if len(self.data.shape) == 3 else 1
        self.annotation_data = np.zeros((self.height, self.width, 3), dtype='uint8')

    def __str__(self):
        txt = "Pyvision3 Image: {}".format(self.desc)
        txt += "\nWidth: {}, Height: {}, Channels: {}, Depth: {}".format(self.width, self.height,
                                                                    self.nchannels, self.data.dtype)
        return txt

    def __repr__(self):
        return str(self)

    def __getitem__(self, slc):
        return self.data[slc]

    def as_annotated(self, alpha=0.5):
        '''
        Provides an array which represents the merging of the image data
        with the annotations layer.

        Parameters
        ----------
        alpha: float between 0.0 and 1.0
            This is the alpha blend when merging the annotations layer onto the image data.
            1.0 means that the annotation will be completely opaque and 0.0 completely transparent.

        Returns
        -------
        A copy of the image array (possibly expanded to 3 channels if the
        original image is single channel) with the color annotations baked in by
        replacing those pixels in the image with the corresponding non-zero pixels
        in the annotation data.
        '''
        # TODO: What if self.data is a floating point image and the annotations
        # are uint8 BGR? We should probably call a normalizing routine of some
        # sort that copies/converts self.data into a 3-channel BGR 8-bit image
        mask = self.annotation_data.nonzero()
        if self.nchannels == 1:
            tmp_img = cv2.cvtColor(self.data, cv2.COLOR_GRAY2BGR)
        else:
            tmp_img = self.data.copy()
        tmp_img[mask] = alpha * self.annotation_data[mask] + (1 - alpha) * tmp_img[mask]
        return tmp_img

    def annotate_shape(self, shape, color=(255, 0, 0), fill_color=None, *args, **kwargs):
        '''
        Draws the specified shape on the annotation data layer.
        Currently supports LineString, MultiLineString, LinearRing,
        and Polygons.

        Parameters
        ----------
        shape: shapely.geometry shape object
        color:
            An RGB tuple indicating the color, red is (255,0,0)
        fill_color:
            The color used to fill a closed shape (polygon). None means
            that there will be no fill (default).

        *args and **kwargs are for optional line parameters that will
        be passed onto cv2.line(...) which is used at the core for
        drawing the line segments of the shape.

        Note
        ----
        OpenCV stores images in BGR not RGB order, thus the annotation
        layer will be constructed this way. However, to make it easier for the
        user, colors to be used are specified in the normal (r,g,b) tuple order,
        and internally, we handle it.
        '''
        # TODO: annotate_shape should support all shapely geometries
        # TODO: annotations should support alpha-channel fills for partial transparency
        if isinstance(shape, sg.LinearRing) or isinstance(shape, sg.LineString):
            self._draw_segments(shape, color, *args, **kwargs)
        elif isinstance(shape, sg.MultiLineString):
            for line_string in shape:
                self._draw_segments(line_string, color, *args, **kwargs)
        elif isinstance(shape, sg.Polygon):
            if fill_color is not None:
                # use cv2.fillPoly
                c = self._fix_color_tuple(fill_color)
                exterior = np.array(shape.exterior.coords, dtype='int')
                interiors = [np.array(x.coords, dtype='int') for x in shape.interiors]
                cv2.fillPoly(self.annotation_data, [exterior] + interiors, color=c)
            # draw external ring of polygon
            self._draw_segments(shape.exterior, color, *args, **kwargs)
            # draw interior rings (holes) if any
            for interior_ring in shape.interiors:
                self._draw_segments(interior_ring, color, *args, **kwargs)

    def annotate_point(self, point, color=(255, 0, 0)):
        '''
        Annotates a point by drawing a filled circle of radius-3 pix in the annotation
        layer.
        '''
        self.annotate_circle(point, 3, color, thickness=-1)

    def annotate_circle(self, ctr, radius, color=(255, 0, 0), *args, **kwargs):
        '''
        Draws a circle on the annotation layer

        Parameters
        ----------
        ctr: (int: x, int: y)
            the center points of the circle

        radius: int
            the radius in pixels of the circle

        color: (r,g,b)

        *args and **kwargs will be passed onto cv2.circle function, and
        can be used to control the thickness and line type. Note that a negative
        thickness indicates that the circle will be filled.
        '''
        c = self._fix_color_tuple(color)
        ctr = (int(ctr[0]), int(ctr[1]))
        cv2.circle(self.annotation_data, ctr, radius, c, *args, **kwargs)

    def annotate_line(self, pt1, pt2, color, *args, **kwargs):
        '''
        Draws a line segment between two points on the annotation layer.

        Parameters
        ----------
        pt1, pt2: tuples, (int: x, int: y)
            The start and end points of the line segment

        color: tuple (r,g,b)

        *args and **kwargs will be passed onto cv2.line, which can be
        used to control line thickness and style
        '''
        c = self._fix_color_tuple(color)
        cv2.line(self.annotation_data, pt1, pt2, c, *args, **kwargs)

    def annotate_rect(self, pt1, pt2, color=(255, 0, 0), *args, **kwargs):
        '''
        Draws a rectangle using upper left (pt1) and lower right (pt2) coordinates.
        To fill the rectangle, specify thickness=-1 in the kwargs.
        '''
        c = self._fix_color_tuple(color)
        cv2.rectangle(self.annotation_data, pt1, pt2, color=c, *args, **kwargs)

    def annotate_text(self, txt, point, color=(0, 0, 0), bg_color=None,
                      fontFace=cv2.FONT_HERSHEY_PLAIN, fontScale=1, *args, **kwargs):
        '''
        Draws the specified text string to the annotations layer, uses cv2.putText() function
        as the basis, so *args and **kwargs will be passed onto that function.
        '''
        c = self._fix_color_tuple(color)
        if bg_color is not None:
            # we will draw a filled rectangle of this color to be behind
            # the annotated text
            ((w, h), _) = cv2.getTextSize(txt, fontFace, fontScale, thickness=1)
            point1 = (point[0] - 1, point[1] + 1)
            point2 = (point1[0] + w + 2, point1[1] - h - 2)
            self.annotate_rect(point1, point2, color=bg_color, thickness=-1)

        cv2.putText(self.annotation_data, txt, point, fontFace=fontFace,
                    fontScale=fontScale, color=c, *args, **kwargs)

    def _draw_segments(self, simple_shape, color, *args, **kwargs):
        '''
        Internal method for drawing a "simple" shapely geometric object,
        i.e., one that has a single set of coordinates which will be
        connected in sequence. Examples are LineStrings and LinearRings,
        the latter being a closed sequence of points and the former is not.
        '''
        points = [(int(x), int(y)) for (x, y) in simple_shape.coords]
        for i in range(1, len(points)):
            pt1 = points[i - 1]
            pt2 = points[i]
            self.annotate_line(pt1, pt2, color, *args, **kwargs)

    def _fix_color_tuple(self, color):
        '''
        Puts the color tuple (r,g,b) into (b,g,r) order. Replaces any zeros with ones,
        because the way we composite the annotation layer onto the image only looks for
        non-zero values.
        '''
        (r, g, b) = color
        r = 1 if r == 0 else r
        g = 1 if g == 0 else g
        b = 1 if b == 0 else b
        return (b, g, r)

    def show(self, window_title=None, highgui=False, annotations=True, annotations_opacity=0.5,
             delay=0, pos=None):
        '''
        Displays this image in a highgui or matplotlib window.

        Parameters
        ----------
        window_title: string or None
            If None (default) then the image title will be self.desc, otherwise
            specify a string to be used for this purpose.
        highgui: boolean
            If True then opencv highgui library is used to display the image.
            Otherwise (default) the current figure of matplotlib will be used.
        annotations: boolean
            If True (default) then the annotations will be shown over the base image,
            otherwise only the base image will be shown.
        annotations_opacity: float (0.0 - 1.0)
            Controls the opacity of the annotations layer, assuming annotations=True.
            0.0 means that the annotations will be invisible and 1.0 means completely opaque.
            Default is 0.5.
        delay: int
            The delay in milliseconds to wait after showing the image. This is passed on
            to cv2.waitKey if highgui is specified as the display. This is useful if
            showing a sequence of images as if they were a video.
        pos: tuple (x,y)
            Used if showing via highgui, this is the window's upper left position on
            the user's screen. Default is None, which means the window will be placed
            automatically.
        '''
        if not window_title:
            window_title = self.desc

        img_array = self.as_annotated(alpha=annotations_opacity) if annotations \
                    else self.data.copy()
        # optional resize logic here?

        if highgui:
            # display via  an opencv window
            # Create the window
            cv2.namedWindow(window_title)

            # Set the location
            if pos is not None:
                cv2.moveWindow(window_title, pos[0], pos[1])

            # Display the result
            cv2.imshow(window_title, img_array)
            key = cv2.waitKey(delay=delay)
            del img_array
            return key
        else:
            # display in a matplotlib figure
            if img_array.shape[-1] == 3:
                # Note cv2 image arrays are BGR order, but matplotlib expects
                # RGB order. So we're swapping channel 0 with channel 2
                tmp = img_array[:, :, 0].copy()
                img_array[:, :, 0] = img_array[:, :, 2]
                img_array[:, :, 2] = tmp
                del tmp
            plot.imshow(img_array)
            plot.title(window_title)
            plot.draw()
            plot.show(block=False)

    def save(self, filename, *args, as_annotated=True, **kwargs):
        '''
        Saves the image data (or the annotated image data) to a file.
        This wraps cv2.imwrite function.

        Parameters
        ----------
        filename: String
            The filename, including extension, for the saved image
        as_annotated: Boolean
            If True (default) then the annotated version of the image will be saved.
        All other args and kwargs are passed on to cv2.imwrite
        '''
        img_array = self.as_annotated() if as_annotated else self.data
        cv2.imwrite(filename, img_array, *args, **kwargs)
