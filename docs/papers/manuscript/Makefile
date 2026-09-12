.PHONY: all

all: paper.pdf

paper.pdf: $(wildcard *.tex) references.bib Makefile
	PATH="/Library/TeX/texbin:$$PATH" latexmk -pdf -interaction=nonstopmode -halt-on-error -jobname=paper -outdir=build main.tex
	mv -f build/paper.pdf paper.pdf
