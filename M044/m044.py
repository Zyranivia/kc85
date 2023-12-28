import os
import sys

from pathlib import Path
from collections import namedtuple
from colorama import init, Fore, Style

# https://stackoverflow.com/a/40424449/8038465
init(convert=True)

FileContent = namedtuple("FileContent", "file_name content start_pos")

class InputError(Exception):
	def __init__(self, english, german = ""):
		error = german if (german != "") else english
		super().__init__(
			f"{Fore.RED}Ein Fehler ist aufgetreten{Style.RESET_ALL}\n\n" + error
		)

def program_version():
	return "1.0"

def comment_character():
	return "#"

def parse_starting_pos(as_string):
	as_string = as_string.replace('_', '')
	value = int(as_string, 16)

	if value < 0:
		raise InputError(
			f"file position must be non-negative (was '{as_string}')",
			f"Fileposition muss nicht-negativ sein (gelesen wurde '{as_string}')"
		)

	if value % 8192 != 0:
		raise InputError(
			f"file position must be a multiple of 2000h (was '{as_string}')",
			f"Fileposition muss ein Vielfaches von 2000h sein (gelesen wurde '{as_string}')"
		)
	return value

def get_file_contents(input_file_list):

	with open(input_file_list, "r") as file:
		files = file.readlines()
		# support comments
		files = [filename.split(comment_character())[0] for filename in files]
		# support extraneous whitespace
		files = [filename.rstrip() for filename in files if filename.rstrip() != ""]

	if len(files) == 0:
		raise InputError(
			f"output file missing in {str(input_file_list)}",
			f"In {str(input_file_list)} wurde keine Ausgabedatei definiert"
		)
	
	try:
		output_file_splits = files[0].split()
		assert(len(output_file_splits) == 2)
		output_file_size_in_MB = int(output_file_splits[0])
		assert(output_file_size_in_MB in [1, 2, 4, 8])
		output_file = Path(output_file_splits[1])

	except Exception as e:
		raise InputError(
			f"output file definition does not meet the requirements due to '{str(e)}'",
			f"Die Definition der Ausgabedatei genügt nicht den Anforderungen: '{str(e)}'"
		)

	if len(files) == 1:
		raise InputError(
			f"no input files were specified in {str(input_file_list)}",
			f"In {str(input_file_list)} wurden keine Inputdateien definiert"
		)

	files = files[1:]

	contents = []
	for file in files:
		file_splits = file.split()
		assert(len(file_splits) == 2)
		starting_pos = parse_starting_pos(file_splits[0])
		filepath = input_file_list.parent / file_splits[1]

		if not filepath.is_file():
			raise InputError(
				f"{str(filepath)} does not exist or is not a file",
				f"{str(filepath)} existiert nicht oder ist keine Datei"
			)

		with open(filepath, "rb") as file: # read bytes
			contents.append(FileContent(filepath.name, file.read(), starting_pos))
	
	return output_file, output_file_size_in_MB, contents

def write_file(output_file, output_file_size_in_MB, contents):
	output_file.unlink(missing_ok=True)
	output_file_size = output_file_size_in_MB * 1024 * 1024

	sorted(contents, key=lambda x: x.start_pos)

	with open(output_file, "ab") as file:
		current_file_size = 0
		for file_content in contents:
			if current_file_size > file_content.start_pos:
				raise InputError(
					f"'{file_content.file_name}' would overwrite parts of the previous file",
					f"'{file_content.file_name}' würde Teile des vorherigen Files überschreiben"
				)

			file.write(b'\xff' * (file_content.start_pos - current_file_size))
			file.write(file_content.content)
			current_file_size = file_content.start_pos + len(file_content.content)
		
		if current_file_size > output_file_size:
			raise InputError(
				f"writing all files would result in a bigger file than {output_file_size_in_MB} MiByte",
				f"Alle Files zu schreiben führt zu einem größeren File als {output_file_size_in_MB} MiByte"
			)
		file.write(b'\xff' * (output_file_size - current_file_size))

	assert(output_file.stat().st_size == output_file_size)


def main():
	print(f"This is version {program_version()}\n")

	if len(sys.argv) != 2:
		print(f"Usage: python3 {sys.argv[0]} [input_file_list]")
		sys.exit()

	try:
		output_file, output_file_size_in_MB, contents = get_file_contents(Path(sys.argv[1]))
		write_file(output_file, output_file_size_in_MB, contents)

		print(f"'{str(output_file)}' wurde erfolgreich erzeugt")
		sys.exit(0)
	
	except InputError as e:
		print(str(e))
		sys.exit(1)


if __name__ == "__main__":
	main()
