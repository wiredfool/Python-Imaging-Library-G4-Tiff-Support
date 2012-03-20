/*
 * The Python Imaging Library.
 * $Id: //modules/pil/libImaging/Tiff.h#1 $
 *
 * declarations for the LibTiff-based Group3 and Group4 decoder
 *
 */

#include <tiffio.h>
#include <tiff.h>

#define min(x,y) (( x > y ) ? y : x )
#define max(x,y) (( x < y ) ? y : x )

typedef struct {
	tdata_t data; /* tdata_t == void* */
	toff_t loc;   /* toff_t == uint32 */
	tsize_t size; /* tsize_t == int32 */
	int fp;
	TIFF *tiff; /* Used in write */
	toff_t eof;
	int flrealloc; /* may we realloc */
} TIFFSTATE;


extern int ImagingLibTiffInit(ImagingCodecState state, int compression, int fp);

extern int ImagingLibTiffEncodeInit(ImagingCodecState state, char *filename, int fp);
extern int ImagingLibTiffSetField(ImagingCodecState state, ttag_t tag, ...);


#define VA_ARGS(...)	__VA_ARGS__
#define TRACE(args)    fprintf(stderr, VA_ARGS args)


/* 
#define TRACE(args)
*/
