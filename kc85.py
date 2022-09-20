import math
import os
import sys

from pathlib import Path
from collections import namedtuple
from colorama import init, Fore, Style

# https://stackoverflow.com/a/40424449/8038465
init(convert=True)

FileContent = namedtuple("FileContent", "filename content starting_sector")

class InputError(Exception):
	def __init__(self, english, german = ""):
		super().__init__(
			f"{Fore.RED}An error has been encountered | Ein Fehler ist aufgetreten{Style.RESET_ALL}\n\n" +
			english + "\n\n" + german
		)

def program_version():
	return "1.3"

def comment_character():
	return "#"

def get_config(modus):
	base_config = {
		"directory_entry_size": 16,
		"max_stem_size"       : 8,
		"max_extension_size"  : 3,
		"cluster_size"        : 16 * 1024,
		"padding_size"        : 4  * 1024,
		"sector_size"         : 128
	}
	
	if (modus == "M048"):
		base_config["max_number_of_files"] = 32
		base_config["final_file_size"]     = 256 * 1024
		return base_config

	if (modus == "M049"):
		base_config["max_number_of_files"] = 64
		base_config["final_file_size"]     = 512 * 1024
		return base_config

	raise InputError(
		f"Only 'M048' or 'M049' supported, '{modus}'' was entered",
		f"Nur 'M048' oder 'M049' werden unterstützt, '{modus}'' wurde eingegeben"
	)


def get_modus_and_updated_outputfile(outputfile):
	stem, extension = os.path.splitext(outputfile.name)

	if (extension != ".ROM"):
		outputfile = Path(str(outputfile) + ".ROM")

	modi = ["M048", "M049"]
	for modus in modi:
		if (stem.startswith(modus)):
			return modus, outputfile

	raise InputError(
		f"output file ({outputfile.name}) has to begin with one element in {modi}",
		f"Name der Ausgabedatei ({outputfile.name}) darf nur mit einem Element aus folgender Liste beginnen: {modi}"
	)


def resolve_name(filepath):
	resolved_name = filepath.name
	stem, extension = os.path.splitext(resolved_name)

	if (len(stem) > 8):
		raise InputError(
			f"stem '{stem}' of '{resolved_name}' is longer than 8 characters",
			f"Dateiname '{stem}' von '{resolved_name}' ist länger als 8 Zeichen"
		)
	if (len(extension) > 4):
		raise InputError(
			f"extension '{extension[1:]}' of '{resolved_name}' is longer than 3 characters",
			f"Extension '{extension[1:]}' bon '{resolved_name}' ist länger als 3 Zeichen"
		)

	try:
		resolved_name.encode("ascii")
	except UnicodeEncodeError as e:
		raise InputError(
			f"only the first 128 ascii characters are allowed, '{resolved_name}' contains forbidden ones",
			f"Nur die ersten 128 ASCII-Zeichen sind erlaubt, '{resolved_name}' enthält nicht erlaubte Zeichen"
		)
	
	return resolved_name


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

	if len(files) == 1:
		raise InputError(
			f"no input files were specified in {str(input_file_list)}",
			f"In {str(input_file_list)} wurden keine Inputdateien definiert"
		)

	outputfile = Path(files[0])
	modus, outputfile = get_modus_and_updated_outputfile(outputfile)
	files = files[1:]

	config = get_config(modus)
	max_number_of_files = config["max_number_of_files"]
	
	if len(files) > max_number_of_files:
		raise InputError(
			f"{len(files)} entries are more than the {max_number_of_files} allowed",
			f"{len(files)} Einträge sind mehr als die {max_number_of_files} erlaubten"
		)

	if len(files) > len(set(files)):
		raise InputError(
			f"entries of {str(input_file_list)} are not unique",
			f"In {str(input_file_list)} kommen Einträge mehrfach vor"
		)

	contents = []
	for filename in files:
		filepath = input_file_list.parent / filename
		resolved_name = resolve_name(filepath)

		if not filepath.is_file():
			raise InputError(
				f"{str(filepath)} does not exist or is not a file",
				f"{str(filepath)} existiert nicht oder ist keine Datei"
			)

		with open(filepath, "rb") as file: # read bytes
			contents.append(FileContent(resolved_name, file.read(), -1))
	
	return outputfile, modus, contents

# ensure if there is space for the directory, we provide it
def move_smallest_file_to_back(modus, contents):
	config = get_config(modus)
	padding_size = config["padding_size"]

	# minus one as exactly padding_size is the worst case; avoid underflow
	val, idc = min((max(0, len(content[1]) - 1) % padding_size, idx) for (idx, content) in enumerate(contents))
	contents[-1], contents[idc] = contents[idc], contents[-1]
	return idc

def get_current_starting_sector(modus, filehook):
	config = get_config(modus)
	filehook.seek(0, os.SEEK_END)
	return filehook.tell() // config["sector_size"]

def write_files_with_padding(modus, contents, outputfile):
	config = get_config(modus)
	padding_size = config["padding_size"]
	final_file_size = config["final_file_size"]

	outputfile.unlink(missing_ok=True)

	new_contents = [] # with updated starting_sector
	with open(outputfile, "ab") as file:
		for file_content in contents:
			new_contents.append(FileContent(
				file_content.filename,
				file_content.content,
				get_current_starting_sector(modus, file)
			))

			file.write(file_content.content)
			file.write(b'\0' * (padding_size - len(file_content.content) % padding_size))

	file_size = outputfile.stat().st_size
	if file_size > final_file_size:
		raise InputError(
			f"fitting all files results in {file_size / 1024} kb, which is more than the {final_file_size / 1024} kb allowed",
			f"Alle Einträge zusammen ergeben {file_size / 1024} kb, was mehr ist als die erlaubten {final_file_size / 1024} kb"
		)

	return new_contents


def pad_file_until_directory_with_dummy_rom(modus, contents, outputfile):
	config = get_config(modus)
	final_size = config["final_file_size"]
	padding_size = config["padding_size"]
	max_number_of_files = config["max_number_of_files"]

	space_need_for_directory = max_number_of_files * config["directory_entry_size"]

	file_size_after_contents = outputfile.stat().st_size

	free_space_in_padding_size = (final_size // padding_size) - (file_size_after_contents // padding_size)
	if (free_space_in_padding_size > 0):
		# defensive estimation that the directory is in its own block
		assert(space_need_for_directory <= config["padding_size"])
		free_space_in_padding_size = free_space_in_padding_size - 1
	assert(free_space_in_padding_size >= 0)

	if file_size_after_contents == final_size:
		# can we still fit the directory?
		space_left = padding_size - (len(contents[-1].content) % padding_size)
		if space_left < space_need_for_directory:
			raise InputError(
				f"cannot fit directory :/",
				f"Kein Platz mehr für das Verzeichnis :/"
			)
	else:
		assert(len(contents) <= max_number_of_files)
		if (len(contents) == max_number_of_files):
			raise InputError(
				f"Maximum number of entries ({max_number_of_files}) was used, but there is still unused space. Please remove at least on entry.",
				f"Die Maximalanzahl an Einträge ({max_number_of_files}) wurde genutzt, es gibt jedoch noch ungenutzten Platz. Bitte entferne wenigstens einen Eintrag."
			)

		with open(outputfile, "ab") as file:
			# add dummy file to fill out remaining space
			dummy_content = b'\xe5' * (final_size - file_size_after_contents)
			contents.append(FileContent(
				"DUMMY.ROM",
				dummy_content,
				get_current_starting_sector(modus, file)
			))
			file.write(dummy_content)

	assert(outputfile.stat().st_size == final_size)

	with open(outputfile, "r+b") as file:
		file.seek(-space_need_for_directory, os.SEEK_END)
		file.truncate()

	return free_space_in_padding_size


def get_bit(value, bit):
	return int((value & (1 << bit)) != 0)

def set_bit(value, bit):
	return value | (1 << bit)


def create_directory_entry(modus, file_content):
	config = get_config(modus)

	stem, extension = os.path.splitext(file_content.filename)
	assert(extension[0] == ".")
	extension = extension[1:]

	# byte 0: empty
	result = bytearray(b'\x01') # \x01 or \x0f
	# byte 1-8: stem
	result += stem.encode("ascii")
	result += (b'\x20' * (config["max_stem_size"] - len(stem)))
	# byte 9-11: extension
	result += extension.encode("ascii")
	result += (b'\x20' * (config["max_extension_size"] - len(extension)))
	# byte 12: number cluster 0-indexed
	num_cluster = len(file_content.content) // config["cluster_size"]
	result += num_cluster.to_bytes(1, byteorder='little')
	# byte 13-14: starting sector, 0-indexed
	assert(file_content.starting_sector != -1)
	result += file_content.starting_sector.to_bytes(2, byteorder='little')
	# byte 15: 128 byte sectors into last cluster, 1-indexed
	num_remainder = int(math.ceil((len(file_content.content) % config["cluster_size"]) / 128))
	result += num_remainder.to_bytes(1, byteorder='little')

	# file attributes are defined by the highest order bit of the stem and extension
	assert(all([get_bit(byte, 7) == 0 for byte in result[1:12]]))
	for byte_to_set in [2, 8, 9]:
		result[byte_to_set] = set_bit(result[byte_to_set], 7)

	assert(len(result) == get_config(modus)["directory_entry_size"])
	return result


def write_directory(modus, contents, outputfile, swapped_with_back_id):
	config = get_config(modus)
	space_need_for_directory = config["max_number_of_files"] * config["directory_entry_size"]

	free_space_in_padding_size = pad_file_until_directory_with_dummy_rom(modus, contents, outputfile)
	assert(outputfile.stat().st_size == (config["final_file_size"] - space_need_for_directory))

	with open(outputfile, "ab") as file:
		entries = [create_directory_entry(modus, file_content) for file_content in contents]
		# swap smallest entry back in directory so they appear in order
		entries[-1], entries[swapped_with_back_id] = entries[swapped_with_back_id], entries[-1]

		for entry in entries:
			file.write(entry)

		empty_directory_entries = config["max_number_of_files"] - len(contents)
		file.write(b'\xe5' * empty_directory_entries * 16)

	assert(outputfile.stat().st_size == config["final_file_size"])
	return free_space_in_padding_size


def main():
	print(f"This is version {program_version()}\n")

	if len(sys.argv) != 2:
		print(f"Usage: python3 {sys.argv[0]} [input_file_list]")
		sys.exit()

	try:
		outputfile, modus, contents = get_file_contents(Path(sys.argv[1]))
		config = get_config(modus)

		swapped_with_back_id = move_smallest_file_to_back(modus, contents)
		contents = write_files_with_padding(modus, contents, outputfile)
		free_space_in_padding_size = write_directory(modus, contents, outputfile, swapped_with_back_id)

		initial_space_in_padding_size = config["final_file_size"] // config["padding_size"]

		contains_dummy_file = (free_space_in_padding_size != 0)
		msg = f"'{str(outputfile)}' has successfully been created, containing {len(contents)} programs"
		if (contains_dummy_file):
			msg += (f" (including one dummy file)")
		msg += "."
		msg += f"\nThere are {free_space_in_padding_size}/{initial_space_in_padding_size} blocks of {config['padding_size']} bytes still unused."
		msg += f" (= {free_space_in_padding_size * config['padding_size'] // 1024} kiByte)"

		msg += "\n\n"

		msg += f"'{str(outputfile)}' wurde erfolgreich erzeugt und enthält {len(contents)} Programme"
		if (contains_dummy_file):
			msg += (f" (inklusive einer Dummy-Datei)")
		msg += "."
		msg += f"\nEs gibt noch {free_space_in_padding_size}/{initial_space_in_padding_size} ungenutzte Blöcke zu je {config['padding_size']} bytes."
		msg += f" (= {free_space_in_padding_size * config['padding_size'] // 1024} kiByte)"
		print(msg)
		sys.exit(0)

	except InputError as e:
		print(str(e))
		sys.exit(1)


if __name__ == "__main__":
	main()
