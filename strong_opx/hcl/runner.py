import os
import subprocess
from typing import TYPE_CHECKING, Any

from strong_opx.exceptions import UndefinedVariableError
from strong_opx.hcl.extractor import HCLVariableExtractor
from strong_opx.utils.shell import shell

if TYPE_CHECKING:
    from strong_opx.project import Environment


class HCLRunner:
    extension: str
    env_var_prefix: str

    def __init__(self, environment: "Environment", directory: str):
        self.environment = environment
        self.directory = directory

    @staticmethod
    def _serialize_value(value: Any) -> str:
        """
        Converts a variable value to a string that can be used as an environment variable that will be passed to a
        Terraform or Packer command.

        Per Terraform documentation:
        https://developer.hashicorp.com/terraform/cli/commands/plan#input-variables-on-the-command-line

        string, number, and bool values are expected to be passed as strings with no special punctuation. For all other
        type constraints, including list, map, and set types and the special any keyword, you must write a valid
        Terraform language expression representing the value, and write any necessary quoting or escape characters to
        ensure it will pass through your shell literally to Terraform.

        Packer documentation does not explicitly call this out, but, in testing, this code works for Packer as well.

        NOTE: This method does NOT handle Windows command line escaping, so it should only be used in Unix environments.
        strong-opx does not currently support Windows, but I wanted to explicitly call it out here.
        """
        if isinstance(value, list) or isinstance(value, tuple):
            build_string = "["
            for item in value:
                if isinstance(item, str):
                    build_string += f'"{item}",'
                else:
                    build_string += f"{HCLRunner._serialize_value(item)},"
            if build_string.endswith(","):
                build_string = build_string[:-1]  # remove trailing comma
            build_string += "]"
            return build_string

        if isinstance(value, dict):
            build_string = "{"
            for key, val in value.items():
                if isinstance(val, str):
                    build_string += f'"{key}": "{val}",'
                else:
                    build_string += f'"{key}": {HCLRunner._serialize_value(val)},'
            if build_string.endswith(","):
                build_string = build_string[:-1]  # remove trailing comma

            build_string += "}"

            return build_string

        if isinstance(value, bool):
            return str(value).lower()

        return str(value)

    def extract_vars(self) -> dict[str, str]:
        env_dict = {}
        extractor = HCLVariableExtractor()

        context = self.environment.context

        for filename in os.listdir(self.directory):
            if filename.endswith(self.extension):
                file_path = os.path.join(self.directory, filename)
                with open(file_path) as f:
                    extractor.extract(file_path, f)

        missing_vars = []
        for var in extractor.required_vars:
            if var not in context:
                missing_vars.append(var)
                continue

            env_dict[f"{self.env_var_prefix}_{var}"] = self._serialize_value(context[var])

        if missing_vars:
            raise UndefinedVariableError(*missing_vars)

        for var in extractor.optional_vars:
            if var in context:
                env_dict[f"{self.env_var_prefix}_{var}"] = self._serialize_value(context[var])

        return env_dict

    def get_executable(self) -> str:
        raise NotImplementedError()

    def _run(self, args: tuple[str, ...], env: dict[str, str], **kwargs) -> subprocess.CompletedProcess:
        return shell(args, env=env, cwd=self.directory, **kwargs)

    def run(
        self, command: str, env: dict[str, str] = None, additional_args: tuple[str, ...] = ()
    ) -> subprocess.CompletedProcess:
        if env is None:
            env = dict(os.environ)

        env.update(self.extract_vars())
        args = (self.get_executable(), command, *additional_args)
        return self._run(args, env=env)
