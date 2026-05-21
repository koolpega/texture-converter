from flask import (
    Flask,
    render_template,
    request,
    send_file,
    jsonify,
    url_for
)

from PIL import Image

import texture2ddecoder
import struct
import os
import uuid
import traceback

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

def convert_ktx_to_png(
    input_path,
    output_path
):

    with open(input_path, 'rb') as f:

        header = f.read(64)

        if len(header) < 64:

            raise Exception(
                "Invalid KTX file"
            )

        magic = header[:12]

        if magic != b'\xABKTX 11\xBB\r\n\x1A\n':

            raise Exception(
                "Not a valid KTX file"
            )

        gl_internal_format = struct.unpack(
            '<I',
            header[28:32]
        )[0]

        width = struct.unpack(
            '<I',
            header[36:40]
        )[0]

        height = struct.unpack(
            '<I',
            header[40:44]
        )[0]

        bytes_of_kv = struct.unpack(
            '<I',
            header[60:64]
        )[0]

        f.seek(
            64 + bytes_of_kv
        )

        image_size = struct.unpack(
            '<I',
            f.read(4)
        )[0]

        data = f.read(image_size)

    print(
        "FORMAT:",
        hex(gl_internal_format)
    )

    if gl_internal_format == 0x8D64:

        decoded = texture2ddecoder.decode_etc1(
            data,
            width,
            height
        )

    elif 0x93B0 <= gl_internal_format <= 0x93BD:

        astc_formats = {

            0x93B0: (4, 4),
            0x93B1: (5, 4),
            0x93B2: (5, 5),
            0x93B3: (6, 5),
            0x93B4: (6, 6),
            0x93B5: (8, 5),
            0x93B6: (8, 6),
            0x93B7: (8, 8),
            0x93B8: (10, 5),
            0x93B9: (10, 6),
            0x93BA: (10, 8),
            0x93BB: (10, 10),
            0x93BC: (12, 10),
            0x93BD: (12, 12)

        }

        if gl_internal_format not in astc_formats:

            raise Exception(
                f"Unsupported ASTC format: {hex(gl_internal_format)}"
            )

        bx, by = astc_formats[
            gl_internal_format
        ]

        decoded = texture2ddecoder.decode_astc(
            data,
            width,
            height,
            bx,
            by
        )

    elif gl_internal_format == 0x8058:

        expected = width * height * 4

        if len(data) < expected:

            raise Exception(
                f"Texture data too small.\n"
                f"Expected: {expected}\n"
                f"Found: {len(data)}"
            )

        decoded = data[:expected]

    else:

        raise Exception(
            f"Unsupported format: {hex(gl_internal_format)}"
        )

    img = Image.frombytes(
        "RGBA",
        (width, height),
        decoded
    )

    r, g, b, a = img.split()

    img = Image.merge(
        "RGBA",
        (b, g, r, a)
    )

    img = img.transpose(
        Image.FLIP_TOP_BOTTOM
    )

    img.save(output_path)

def convert_png_to_ktx(
    input_path,
    output_path
):

    img = Image.open(
        input_path
    ).convert("RGBA")

    img = img.transpose(
        Image.FLIP_TOP_BOTTOM
    )

    r, g, b, a = img.split()

    img = Image.merge(
        "RGBA",
        (b, g, r, a)
    )

    width, height = img.size

    pixel_data = img.tobytes()

    kv_key = b"KTXorientation"

    kv_value = b"S=r,T=d"

    kv_pair = (
        kv_key +
        b"\x00" +
        kv_value +
        b"\x00"
    )

    kv_entry = struct.pack(
        '<I',
        len(kv_pair)
    ) + kv_pair

    padding = (
        4 - (
            len(kv_entry) % 4
        )
    ) % 4

    kv_block = kv_entry + (
        b'\x00' * padding
    )

    header = struct.pack(
        '<12sIIIIIIIIIIII',

        b'\xABKTX 11\xBB\r\n\x1A\n',

        0x04030201,

        0x1401,

        1,

        0x1908,

        0x8058,

        0x1908,

        width,

        height,

        0,

        0,

        1,

        len(kv_block)
    )

    with open(output_path, 'wb') as f:

        f.write(header)

        f.write(kv_block)

        f.write(
            struct.pack(
                '<I',
                len(pixel_data)
            )
        )

        f.write(pixel_data)

@app.route("/")
def home():

    return render_template(
        "index.html"
    )

@app.route(
    "/api/convert",
    methods=["POST"]
)
def api_convert():

    try:

        mode = request.form.get(
            "mode"
        )

        file = request.files.get(
            "file"
        )

        if not file:

            return jsonify({

                "success": False,
                "error": "No file uploaded"

            }), 400

        ext = os.path.splitext(
            file.filename
        )[1]

        unique = str(
            uuid.uuid4()
        )

        input_path = os.path.join(
            UPLOAD_FOLDER,
            unique + ext
        )

        file.save(input_path)

        if mode == "ktx_to_png":

            output_filename = (
                unique + ".png"
            )

            output_path = os.path.join(
                UPLOAD_FOLDER,
                output_filename
            )

            convert_ktx_to_png(
                input_path,
                output_path
            )

        elif mode == "png_to_ktx":

            output_filename = (
                unique + ".ktx"
            )

            output_path = os.path.join(
                UPLOAD_FOLDER,
                output_filename
            )

            convert_png_to_ktx(
                input_path,
                output_path
            )

        else:

            return jsonify({

                "success": False,
                "error": "Invalid mode"

            }), 400

        file_url = url_for(
            "uploaded_file",
            filename=output_filename,
            _external=True
        )

        return jsonify({

            "success": True,

            "mode": mode,

            "download": file_url,

            "preview": file_url

        })

    except Exception as e:

        return jsonify({

            "success": False,

            "error": str(e),

            "traceback": traceback.format_exc()

        }), 500

@app.route(
    "/uploads/<filename>"
)
def uploaded_file(filename):

    return send_file(
        os.path.join(
            UPLOAD_FOLDER,
            filename
        )
    )

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000,
        debug=True
    )