"""
For curating data sets consisting of a large number of small images ("tiles" or "crops"),
it can be very handy to have a simple tool for selecting a few of many, such as selecting
bad examples from a set, etc.

This module provides the TileSelector tool, which is based on the underlying pyvision
image montage object and cv2's high gui interface.

author: Stephen O'Hara
created: April 15, 2016
"""
import glob
import os
import pyvision as pv3
import cv2


class TileSelector(object):
    """
    A tile selector instance provides a user interface for selecting some tiles
    out of a larger set, using an image montage display.
    """
    def __init__(self, tile_generator, chunk_size=48, layout=(6, 8)):
        self.tile_gen = tile_generator
        self.chunk_size = chunk_size
        self.layout = layout
        self.selected = []
        self.done = False

    def process_chunk(self, page_num=1):
        tiles = []
        labels = []
        ids = []
        count = 0

        # get chunk_size number of tiles and associated data
        # from the tile generator
        for (id, tile, lbl) in self.tile_gen:
            tiles.append(tile)
            labels.append(lbl)
            ids.append(id)
            count += 1
            if count >= self.chunk_size:
                break

        # if the generator happens to be empty
        if count == 0:
            return

        # if we got here yet count < chunk_size, then
        # the generator must be out of tiles, so we have the
        # final/partial chunk to process
        if count < self.chunk_size:
            self.done = True

        tile_size = tiles[0].size
        imnt = pv3.ImageMontage(tiles, layout=self.layout, tile_size=tile_size,
                                labels=ids, highlight_selected=True)
        imnt.show(window_title="Tile selector: Page {}".format(page_num))
        selected_ids = [ids[x] for x in imnt.get_highlighted()]
        self.selected += selected_ids

    def process_all(self):
        page = 1
        while not self.done:
            self.process_chunk(page_num=page)
            page += 1
        cv2.destroyAllWindows()


def tiles_from_files(filenames, labels=None):
    """
    Returns a tile generator that will generate (id, tile_img, label) tuples by
    reading image tiles from disk.

    Parameters
    ----------
    filenames: list of strings
        The full paths of the image crops to load
    labels: list of strings
        Optional labels to associate with each image tile, must be same length
        as filenames or None, in which case labels will always be None for each tile.

    Returns
    -------
    A generator that yields tuples of the form (id_str, tile_image, label_str) where
    tile_image is a small pyvision image representing the tile, id_str uniquely identifies
    this particular tile, and label_str may be None or a class label/description of some sort.
    """
    if labels is not None:
        assert len(filenames) == len(labels)

    for idx, filen in enumerate(filenames):
        lbl = None if labels is None else labels[idx]
        tile = pv3.Image(filen)
        yield (str(idx), tile, lbl)


def tiles_from_dir(dirname, pattern="*.jpg"):
    """
    Returns a tile generator for all tiles in a directory matching a pattern.
    This uses glob.iglob to read the files, and so it will work efficiently even
    when there are many thousands of files to process. However, the files will
    be processed in arbitrary / non-sorted order. If you wish to process a sorted
    list, use tiles_from_files instead and pregenerate and sort the file names.

    Parameters
    ----------
    dirname: str
        Directory holding the images to yield
    pattern
        Match string, defaults to "*.jpg" for determining which files to include.

    Returns
    -------
    A tile generator, yielding tuples like: (index_str, tile_image, base_file_name)
    """
    filenames = glob.iglob(os.path.join(dirname, pattern))
    idx = 0
    for filen in filenames:
        lbl = os.path.basename(filen)
        tile = pv3.Image(filen)
        yield (str(idx), tile, lbl)
        idx += 1


def tiles_from_vid(pv_video, start_frame=0, end_frame=None):
    """
    A tile generator from a pyvision video object

    Parameters
    ----------
    pv_video: pyvision video
        You may want to use the size= option in the constructor
        of the video so that tile-sized images are generated
    start_frame: int
        Starting frame, defaults to 0
    end_frame: int
        Ending frame, defaults to None, meaning to use the
        complete duration of the video

    Returns
    -------
    A tile generator, yielding tuples like: (str(frame_num), image, None)
    """
    start_frame = 0 if start_frame < 0 else start_frame
    if start_frame != pv_video.current_frame_num:
        pv_video.seek_to(start_frame)
    for tile in pv_video:
        if end_frame is not None:
            if pv_video.current_frame_num > end_frame:
                raise StopIteration
        yield (str(pv_video.current_frame_num), tile, None)
