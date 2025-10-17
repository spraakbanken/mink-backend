# Generating PDF Documentation

To generate the PDF documentation, ensure that `pandoc` and a LaTeX distribution are installed on your
system. The development server should be running at `http://localhost:8000`.

From this directory run the following command:

```bash
./make_pdf.sh
```

The resulting PDF will be saved in the `docs/md2pdf/output` directory. It includes both the Developer's Guide
and the API documentation.

More options are available in the `make-pdf.sh` script. Run `./make-pdf.sh -h` to see them.
