import os
import sys
import glob
import stat
import shutil

from datetime import datetime

import yaml
import dotbot

from dotbot.util import shell_command
from dotbot.plugin import Plugin


class ELink(Plugin):
	"""
	Symbolically links dotfiles.
	"""

	_directive = "elink"

	def can_handle(self, directive):
		return directive == self._directive

	def handle(self, directive, data):
		if directive != self._directive:
			raise ValueError("Link cannot handle directive %s" % directive)
		return self._process_links(data)

	def _process_links(self, links):
		success = True
		defaults = self._context.defaults().get("elink", {})
		for destination, source in links.items():
			destination = os.path.expandvars(destination)
			relative = defaults.get("relative", False)
			# support old "canonicalize-path" key for compatibility
			canonical_path = defaults.get(
				"canonicalize", defaults.get("canonicalize-path", True)
			)
			force = defaults.get("force", False)
			relink = defaults.get("relink", False)
			create = defaults.get("create", False)
			use_glob = defaults.get("glob", False)
			base_prefix = defaults.get("prefix", "")
			test = defaults.get("if", None)
			ignore_missing = defaults.get("ignore-missing", False)
			exclude_paths = defaults.get("exclude", [])
			store_perms = defaults.get("store-perms", True)
			perms_file = defaults.get(
				"perms-file",
				os.path.join(self._context.base_directory(), ".perms.yaml"),
			)
			backup = defaults.get("backup", True)
			backup_dir = defaults.get(
				"backup-dir", os.path.join(self._context.base_directory(), "backups")
			)
			if isinstance(source, dict):
				# extended config
				test = source.get("if", test)
				relative = source.get("relative", relative)
				canonical_path = source.get(
					"canonicalize", source.get("canonicalize-path", canonical_path)
				)
				force = source.get("force", force)
				relink = source.get("relink", relink)
				create = source.get("create", create)
				use_glob = source.get("glob", use_glob)
				base_prefix = source.get("prefix", base_prefix)
				ignore_missing = source.get("ignore-missing", ignore_missing)
				exclude_paths = source.get("exclude", exclude_paths)
				store_perms = source.get("store-perms", store_perms)
				perms_file = source.get("perms-file", perms_file)
				backup = source.get("backup", backup)
				backup_dir = source.get("backup-dir", backup_dir)
				path = self._default_source(destination, source.get("path"))
			else:
				path = self._default_source(destination, source)

			backup_dir = os.path.normpath(
				os.path.expandvars(os.path.expanduser(backup_dir))
			)
			perms_file = os.path.normpath(
				os.path.expandvars(os.path.expanduser(perms_file))
			)

			if test is not None and not self._test_success(test):
				self._log.lowinfo("Skipping %s" % destination)
				continue
			path = os.path.normpath(os.path.expandvars(os.path.expanduser(path)))

			if use_glob and self._has_glob_chars(path):
				glob_results = self._create_glob_results(path, exclude_paths)
				self._log.lowinfo("Globs from '" + path + "': " + str(glob_results))
				for glob_full_item in glob_results:
					# Find common dirname between pattern and the item:
					glob_dirname = os.path.dirname(
						os.path.commonprefix([path, glob_full_item])
					)
					glob_item = (
						glob_full_item
						if len(glob_dirname) == 0
						else glob_full_item[len(glob_dirname) + 1 :]
					)
					# Add prefix to basepath, if provided
					if base_prefix:
						glob_item = base_prefix + glob_item
					# where is it going
					glob_link_destination = os.path.join(destination, glob_item)
					if create:
						success &= self._create(glob_link_destination)
					if backup and self._is_path_regular(
						os.path.abspath(os.path.expanduser(glob_link_destination))
					):
						success &= self._backup(
							glob_full_item,
							glob_link_destination,
							canonical_path,
							backup_dir,
						)
					if force or relink:
						success &= self._delete(
							glob_full_item,
							glob_link_destination,
							relative,
							canonical_path,
							force,
							ignore_missing,
						)
					if (
						ignore_missing
						and not self._exists(glob_link_destination)
						and self._is_link(glob_link_destination)
					):
						self._log.lowinfo(
							f"Link exists {glob_full_item} -> {glob_link_destination}"
						)
						continue
					success &= self._store_perms(
						glob_full_item, perms_file, ignore_missing
					)
					success &= self._link(
						glob_full_item,
						glob_link_destination,
						relative,
						canonical_path,
						ignore_missing,
					)
			else:
				if create:
					success &= self._create(destination)
				if backup and self._is_path_regular(
					os.path.abspath(os.path.expanduser(destination))
				):
					success &= self._backup(
						path,
						destination,
						canonical_path,
						backup_dir,
					)
				if not ignore_missing and not self._exists(
					os.path.join(self._context.base_directory(), path)
				):
					# we seemingly check this twice (here and in _link) because
					# if the file doesn't exist and force is True, we don't
					# want to remove the original (this is tested by
					# link-force-leaves-when-nonexistent.bash)
					success = False
					self._log.warning(
						"Nonexistent source %s -> %s" % (destination, path)
					)
					continue
				if force or relink:
					success &= self._delete(
						path,
						destination,
						relative,
						canonical_path,
						force,
						ignore_missing,
					)
				if (
					ignore_missing
					and not self._exists(destination)
					and self._is_link(destination)
				):
					self._log.lowinfo(f"Link exists {path} -> {destination}")
					continue
				success &= self._store_perms(path, perms_file, ignore_missing)
				success &= self._link(
					path, destination, relative, canonical_path, ignore_missing
				)
		if success:
			self._log.info("All links have been set up")
		else:
			self._log.error("Some links were not successfully set up")
		return success

	def _test_success(self, command):
		ret = shell_command(command, cwd=self._context.base_directory())
		if ret != 0:
			self._log.debug("Test '%s' returned false" % command)
		return ret == 0

	def _default_source(self, destination, source):
		if source is None:
			basename = os.path.basename(destination)
			if basename.startswith("."):
				return basename[1:]
			else:
				return basename
		else:
			return source

	def _has_glob_chars(self, path):
		return any(i in path for i in "?*[")

	def _glob(self, path):
		"""
		Wrap `glob.glob` in a python agnostic way, catching errors in usage.
		"""
		found = glob.glob(path, recursive=True)
		# normalize paths to ensure cross-platform compatibility
		found = [os.path.normpath(p) for p in found]
		# if using recursive glob (`**`), filter results to return only files:
		if "**" in path and not path.endswith(str(os.sep)):
			self._log.debug("Excluding directories from recursive glob: " + str(path))
			found = [f for f in found if os.path.isfile(f)]
		# return matched results
		return found

	def _create_glob_results(self, path, exclude_paths):
		self._log.debug("Globbing with pattern: " + str(path))
		include = self._glob(path)
		self._log.debug("Glob found : " + str(include))
		# filter out any paths matching the exclude globs:
		exclude = []
		for expat in exclude_paths:
			self._log.debug("Excluding globs with pattern: " + str(expat))
			exclude.extend(self._glob(expat))
		self._log.debug("Excluded globs from '" + path + "': " + str(exclude))
		ret = set(include) - set(exclude)
		return list(ret)

	def _is_link(self, path):
		"""
		Returns true if the path is a symbolic link.
		"""
		return os.path.islink(os.path.expanduser(path))

	def _link_destination(self, path):
		"""
		Returns the destination of the symbolic link.
		"""
		path = os.path.expanduser(path)
		path = os.readlink(path)
		if sys.platform[:5] == "win32" and path.startswith("\\\\?\\"):
			path = path[4:]
		return path

	def _exists(self, path):
		"""
		Returns true if the path exists.
		"""
		path = os.path.expanduser(path)
		return os.path.exists(path)

	def _link_not_pointing_to(self, path, target):
		"""
		Returns true if the path is a symbolic link and points to target.
		"""
		return self._is_link(path) and self._link_destination(path) != target

	def _link_points_to(self, path, target):
		"""
		Returns true if the path is a symbolic link and points to target.
		"""
		return self._is_link(path) and self._link_destination(path) == target

	def _is_path_regular(self, path):
		"""
		Returns true if the path exists and it isn't a symbolic link.
		"""
		return self._exists(path) and not self._is_link(path)

	def _resolve_absolute_src(self, source):
		"""
		Returns the absolute path of source.
		"""
		return os.path.join(self._context.base_directory(), source)

	def _create(self, path):
		success = True
		parent = os.path.abspath(os.path.join(os.path.expanduser(path), os.pardir))
		if not self._exists(parent):
			self._log.debug("Try to create parent: " + str(parent))
			try:
				os.makedirs(parent)
			except OSError:
				self._log.warning("Failed to create directory %s" % parent)
				success = False
			else:
				self._log.lowinfo("Creating directory %s" % parent)
		return success

	def _delete(self, source, path, relative, canonical_path, force, ignore_missing):
		success = True
		source = os.path.join(
			self._context.base_directory(canonical_path=canonical_path), source
		)
		fullpath = os.path.abspath(os.path.expanduser(path))
		if relative:
			source = self._relative_path(source, fullpath)
		if (
			self._link_not_pointing_to(path, source)
			or self._is_path_regular(path)
			or (self._link_points_to(path, source) and not ignore_missing)
		):
			removed = False
			try:
				if os.path.islink(fullpath):
					os.unlink(fullpath)
					removed = True
				elif force:
					if os.path.isdir(fullpath):
						shutil.rmtree(fullpath)
						removed = True
					else:
						os.remove(fullpath)
						removed = True
			except OSError:
				self._log.warning("Failed to remove %s" % path)
				success = False
			else:
				if removed:
					self._log.lowinfo("Removing %s" % path)
		return success

	def _backup(self, destination, source, canonical_path, backup_dir):
		success = True
		source = os.path.abspath(os.path.expanduser(source))
		base_directory = self._context.base_directory(canonical_path=canonical_path)
		destination = os.path.join(base_directory, destination)
		source = os.path.normpath(source)

		if self._exists(destination) or self._is_link(destination):
			if not os.path.isdir(backup_dir):
				try:
					os.makedirs(backup_dir)
				except OSError as e:
					self._log.warning(f"{e} at {backup_dir}")
					return False
			filename = (
				os.path.basename(source)
				+ "--"
				+ datetime.now().strftime("%Y-%m-%d-%H-%M")
			)
			dst = os.path.join(backup_dir, filename)
		else:
			dst = destination

		if os.path.exists(dst):
			self._log.lowinfo(f"Destination Already Exists {dst}")
			return True

		copied = False
		try:
			if os.path.isdir(source):
				shutil.copytree(source, dst)
				copied = True
			elif os.path.isfile(source):
				shutil.copy2(source, dst)
				copied = True
			else:
				self._log.warning("Path is neither file nor directory %s" % source)
				return False

			stats = os.stat(source)
			os.chmod(dst, stat.S_IMODE(stats.st_mode))
			os.chown(dst, stats.st_uid, stats.st_gid)
		except Exception as e:
			self._log.warning(f"{e} at {source} -> {dst}")
		else:
			if copied:
				self._log.lowinfo(f"Backing up {source} -> {dst}")

		return success

	def _store_perms(self, source, perms_file, ignore_missing):
		source = os.path.normpath(os.path.expanduser(os.path.expandvars(source)))
		source = self._resolve_absolute_src(source)

		if self._is_link(source) and not os.path.isdir(source):
			self._log.warning(f"Skipping permissions for file symlink {source}")
			return True

		if not self._exists(source):
			self._log.warning(f"Skipping permissions for nonexistent path {source}")
			return ignore_missing

		# ensure perms-file exists
		self._create(os.path.dirname(perms_file))
		with open(perms_file, "a"):
			pass

		try:  # this type of error handling is a stupid and lazy idea
			with open(perms_file) as file:
				data = yaml.safe_load(file) or dict()

			paths = [source]
			if os.path.isdir(source):
				for root, dirs, files in os.walk(source):
					for path in dirs + files:
						paths.append(os.path.join(root, path))

			stored_any = False
			for path in paths:
				if path in data:
					continue
				stats = os.stat(path)
				data[path] = {
					"mode": oct(stat.S_IMODE(stats.st_mode)),
					"uid": stats.st_uid,
					"gid": stats.st_gid,
				}
				self._log.lowinfo(f"Permissions added for {path}.")
				stored_any = True

			if stored_any:
				with open(perms_file, "w") as file:
					yaml.dump(data, file)
				self._log.lowinfo(f"Stored permissions at {perms_file}.")

			return True
		except Exception as e:
			self._log.warning(f"{e} at {source}")
			return False

	def _relative_path(self, source, destination):
		"""
		Returns the relative path to get to the source file from the
		destination file.
		"""
		destination_dir = os.path.dirname(destination)
		return os.path.relpath(source, destination_dir)

	def _link(self, source, link_name, relative, canonical_path, ignore_missing):
		"""
		Links link_name to source.

		Returns true if successfully linked files.
		"""
		success = False
		destination = os.path.abspath(os.path.expanduser(link_name))
		base_directory = self._context.base_directory(canonical_path=canonical_path)
		absolute_source = os.path.join(base_directory, source)
		link_name = os.path.normpath(link_name)
		if relative:
			source = self._relative_path(absolute_source, destination)
		else:
			source = absolute_source
		if (
			not self._exists(link_name)
			and self._is_link(link_name)
			and self._link_destination(link_name) != source
		):
			self._log.warning(
				"Invalid link %s -> %s" % (link_name, self._link_destination(link_name))
			)
		# we need to use absolute_source below because our cwd is the dotfiles
		# directory, and if source is relative, it will be relative to the
		# destination directory
		elif not self._exists(link_name) and (
			ignore_missing or self._exists(absolute_source)
		):
			try:
				os.symlink(source, destination)
			except OSError:
				self._log.warning("Linking failed %s -> %s" % (link_name, source))
			else:
				self._log.lowinfo("Creating link %s -> %s" % (link_name, source))
				success = True
		elif self._exists(link_name) and not self._is_link(link_name):
			self._log.warning(
				"%s already exists but is a regular file or directory" % link_name
			)
		elif self._is_link(link_name) and self._link_destination(link_name) != source:
			self._log.warning(
				"Incorrect link %s -> %s"
				% (link_name, self._link_destination(link_name))
			)
		# again, we use absolute_source to check for existence
		elif not self._exists(absolute_source):
			if self._is_link(link_name):
				self._log.warning("Nonexistent source %s -> %s" % (link_name, source))
			else:
				self._log.warning(
					"Nonexistent source for %s : %s" % (link_name, source)
				)
		else:
			self._log.lowinfo("Link exists %s -> %s" % (link_name, source))
			success = True
		return success
