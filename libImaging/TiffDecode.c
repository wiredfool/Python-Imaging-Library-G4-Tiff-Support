/*
 * The Python Imaging Library.
 * $Id: //modules/pil/libImaging/TiffDecode.c#1 $
 *
 * LibTiff-based Group3 and Group4 decoder
 *
 *
 * started modding to use non-private tiff functions to port to libtiff 4.x
 * eds 3/12/12
 *
 */

#include "Imaging.h"

#ifdef HAVE_LIBTIFF

#undef INT32
#undef UINT32

#include "Tiff.h"


void dump_state(const ClientState *state){
	TRACE(("State: Location %u, size %d, data: %p \n", (uint)state->loc, (int)state->size, state->data));
}

/*
  procs for TIFFOpenClient
*/

tsize_t _tiffReadProc(thandle_t hdata, tdata_t buf, tsize_t size) {
	ClientState *state = (ClientState *)hdata;
	tsize_t to_read;
	
	TRACE(("_tiffReadProc: %d \n", (int)size));
	dump_state(state);

	to_read = min(size, (tsize_t)state->size - state->loc);
	TRACE(("to_read: %d\n", (int)to_read));

	_TIFFmemcpy(buf, state->data, to_read);
	state->loc += (toff_t)to_read;

	TRACE( ("location: %u\n", (uint)state->loc));
	return to_read;
}

tsize_t _tiffWriteProc(thandle_t hdata, tdata_t buf, tsize_t size) {
	/* read only for now */
	return (tsize_t)-1;
}

toff_t _tiffSeekProc(thandle_t hdata, toff_t off, int whence) {
	ClientState *state = (ClientState *)hdata;

	TRACE(("_tiffSeekProc: off: %u whence: %d \n", (uint)off, whence));
	dump_state(state);
	
	return state->loc = off;
}

int _tiffCloseProc(thandle_t hdata) {
	ClientState *state = (ClientState *)hdata;

	TRACE(("_tiffCloseProc \n"));
	dump_state(state);

	//free(state->data);
	//free(state);
	return 0;
}


toff_t _tiffSizeProc(thandle_t hdata) {
	ClientState *state = (ClientState *)hdata;

	TRACE(("_tiffSizeProc \n"));
	dump_state(state);

	return (toff_t)state->size;
}
int _tiffMapProc(thandle_t hdata, tdata_t* pbase, toff_t* psize) {
	ClientState *state = (ClientState *)hdata;

	TRACE(("_tiffMapProc\n"));
	dump_state(state);

	*pbase = state->data;
	*psize = state->size;
	TRACE(("_tiffMapProc returning size: %u, data: %p\n", (uint)*psize, *pbase));
	return (1);
}

void _tiffUnmapProc(thandle_t hdata, tdata_t base, toff_t size) {
	TRACE(("_tiffUnMapProc\n"));
	(void) hdata; (void) base; (void) size;
}

int ImagingLibTiffInit(ImagingCodecState state, int compression) {
	ClientState *clientstate = (ClientState *)state->context;

    TRACE(("initing libtiff\n"));
	TRACE(("Compression: %d\n", compression));
	TRACE(("State: count %d, state %d, x %d, y %d, ystep %d\n", state->count, state->state,
		   state->x, state->y, state->ystep));
	TRACE(("State: xsize %d, ysize %d, xoff %d, yoff %d \n", state->xsize, state->ysize,
		   state->xoff, state->yoff));
	TRACE(("State: bits %d, bytes %d \n", state->bits, state->bytes));
	TRACE(("State: context %p \n", state->context));
		
	clientstate->loc = 0;
	clientstate->size = 0;
	clientstate->data = 0;

    return 1;
}

void ImagingLibTiffCleanup(ImagingCodecState state) {
    return;
}

int ImagingLibTiffDecode(Imaging im, ImagingCodecState state, UINT8* buffer, int bytes) {
	ClientState *clientstate = (ClientState *)state->context;
	char *filename = "tempfile.tif";
	char *mode = "r";
	TIFF *tiff;
	int size;

	/* buffer is the encoded file, bytes is the length of the encoded file */
	/* 	it all ends up in state->buffer, which is a uint8* from Imaging.h */

    TRACE(("in decoder: bytes %d\n", bytes));
	TRACE(("State: count %d, state %d, x %d, y %d, ystep %d\n", state->count, state->state,
		   state->x, state->y, state->ystep));
	TRACE(("State: xsize %d, ysize %d, xoff %d, yoff %d \n", state->xsize, state->ysize,
		   state->xoff, state->yoff));
	TRACE(("State: bits %d, bytes %d \n", state->bits, state->bytes));
	TRACE(("Buffer: %p: %c%c%c%c\n", buffer, (char)buffer[0], (char)buffer[1],(char)buffer[2], (char)buffer[3]));
	TRACE(("State->Buffer: %c%c%c%c\n", (char)state->buffer[0], (char)state->buffer[1],(char)state->buffer[2], (char)state->buffer[3]));
	TRACE(("Image: mode %s, type %d, bands: %d, xsize %d, ysize %d \n",
		   im->mode, im->type, im->bands, im->xsize, im->ysize));
	TRACE(("Image: image8 %p, image32 %p, image %p, block %p \n",
		   im->image8, im->image32, im->image, im->block));
	TRACE(("Image: pixelsize: %d, linesize %d \n",
		   im->pixelsize, im->linesize));
	
	dump_state(clientstate);
	clientstate->size = bytes;
	clientstate->loc = 0;
	clientstate->data = (tdata_t)buffer; 

	dump_state(clientstate);
	
	tiff = TIFFClientOpen(filename, mode,
						  (thandle_t) clientstate,
						  _tiffReadProc, _tiffWriteProc,
						  _tiffSeekProc, _tiffCloseProc, _tiffSizeProc,
						  _tiffMapProc, _tiffUnmapProc);

	if (!tiff){
		TRACE(("Error, didn't get the tiff\n"));
		state->errcode = IMAGING_CODEC_BROKEN;
		return -1;
	}

	size = TIFFScanlineSize(tiff);
	TRACE(("ScanlineSize: %d \n", size));
	if (size > state->bytes) {
		TRACE(("Error, scanline size > buffer size\n"));
		state->errcode = IMAGING_CODEC_BROKEN;
		TIFFClose(tiff);
		return -1;
	}

	// Have to do this row by row and shove stuff into the buffer that way,
	// with shuffle.  (or, just alloc a buffer myself, then figure out how to get it 
	// back in. Can't use read encoded stripe. 
	
	// This thing pretty much requires that I have the whole image in one shot.
	// Prehaps a stub version would work better???
	while(state->y < state->ysize){
		if (TIFFReadScanline(tiff, (tdata_t)state->buffer, (uint32)state->y, 0) == -1) {
			TRACE(("Decode Error, row %d\n", state->y));
			state->errcode = IMAGING_CODEC_BROKEN;
			TIFFClose(tiff);
			return -1;
		}
		/* TRACE(("Decoded row %d \n", state->y)); */
		state->shuffle((UINT8*) im->image[state->y + state->yoff] +
					       state->xoff * im->pixelsize, 
					   state->buffer,
					   state->xsize);
		
		state->y++;
	}

	TIFFClose(tiff);
	TRACE(("Done Decoding, Returning \n"));
	// Returning -1 here to force ImageFile.load to break, rather than
	// even think about looping back around. 
	return -1;	
}

#endif
