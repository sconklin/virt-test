import re, logging
from autotest.client import cgroup_utils
from autotest.client.shared import utils, error
from virttest import virsh


def run_virsh_schedinfo_qemu_posix(test, params, env):
    """
    Test command: virsh schedinfo.

    This version provide base test of virsh schedinfo command:
    virsh schedinfo <vm> [--set<set_ref>]
    TODO: to support more parameters.

    1) Get parameters and prepare vm's state
    2) Prepare test options.
    3) Run schedinfo command to set or get parameters.
    4) Get schedinfo in cgroup
    5) Recover environment like vm's state
    6) Check result.
    """
    def get_parameter_in_cgroup(domname, controller="cpu",
                                parameter="cpu.shares",
                                libvirt_cgroup_path="/libvirt/qemu/"):
        """
        Get vm's cgroup value.

        @Param domname: vm's name
        @Param controller: the controller which parameter is in.
        @Param parameter: the cgroup parameter of vm which we need to get.
        @Param libvirt_cgroup_path: the path of libvirt in cgroup
        @return: False if expected controller is not mounted.
                 else return value's result object.
        """
        try:
            ctl_mount = cgroup_utils.get_cgroup_mountpoint(controller)
        except IndexError:
            return None
        if ctl_mount is not False:
            get_value_cmd = "cat %s/%s/%s/%s" % (ctl_mount,
                                 libvirt_cgroup_path, domname, parameter)
            result = utils.run(get_value_cmd, ignore_status=True)
            return result.stdout.strip()
        else:
            return None


    def schedinfo_output_analyse(result, set_ref, scheduler="posix"):
        """
        Get the value of set_ref.

        @param result: CmdResult struct
        @param set_ref: the parameter has been set
        @param scheduler: the scheduler of qemu(default is posix)
        """
        output = result.stdout.strip()
        if not re.search("Scheduler", output):
            raise error.TestFail("Output is not standard:\n%s" % output)

        result_lines = output.splitlines()
        set_value = None
        for line in result_lines:
            key_value = line.split(":")
            key = key_value[0].strip()
            value = key_value[1].strip()
            if key == "Scheduler":
                if value != scheduler:
                    raise error.TestNAError("This test do not support"
                                            " %s scheduler." % scheduler)
            elif key == set_ref:
                set_value = value
                break
        return set_value


    #Prepare vm test environment
    vm_name = params.get("main_vm")
    vm = env.get_vm(vm_name)
    domid = vm.get_id()
    domuuid = vm.get_uuid()

    #Prepare test options
    vm_ref = params.get("schedinfo_vm_ref", "domname")
    options_ref = params.get("schedinfo_options_ref", "")
    options_suffix = params.get("schedinfo_options_suffix", "")
    set_ref = params.get("schedinfo_set_ref", "")
    cgroup_ref = params.get("schedinfo_cgroup_ref", "")
    set_value = params.get("schedinfo_set_value", "")
    set_value_expected = params.get("schedinfo_set_value_expected", "")
    # The default scheduler on qemu/kvm is posix
    scheduler_value = "posix"
    status_error = params.get("status_error", "no")

    if vm_ref == "domid":
        vm_ref = domid
    elif vm_ref == "domname":
        vm_ref = vm_name
    elif vm_ref == "domuuid":
        vm_ref = domuuid
    elif vm_ref == "hex_id":
        if domid == '-':
            vm_ref = domid
        else:
            vm_ref = hex(int(domid))

    if set_ref == "none":
        options_ref = "--set"
        set_ref = None
    elif set_ref:
        if set_value:
            options_ref = "--set %s=%s" % (set_ref, set_value)
        else:
            options_ref = "--set %s" % set_ref

    options_ref += options_suffix

    # Run command
    result = virsh.schedinfo(vm_ref, options_ref,
                             ignore_status=True, debug=True)
    status = result.exit_status

    # VM must be runnning to get cgroup parameters.
    if not vm.is_alive():
        vm.start()
    set_value_of_cgroup = get_parameter_in_cgroup(vm_name,
                                                  parameter=cgroup_ref)
    vm.destroy()

    if set_ref:
        set_value_of_output = schedinfo_output_analyse(result, set_ref,
                                                       scheduler_value)

    # Check result
    if status_error == "no":
        if status:
            raise error.TestFail("Run failed with right command.")
        else:
            if set_ref and set_value_expected:
                logging.info("value will be set:%s\n"
                             "set value in output:%s\n"
                             "set value in cgroup:%s\n"
                             "expected value:%s" % (
                             set_value, set_value_of_output,
                             set_value_of_cgroup, set_value_expected))
                if set_value_of_output is None:
                    raise error.TestFail("Get parameter %s failed." % set_ref)
                if not (set_value_expected == set_value_of_output):
                    raise error.TestFail("Run successful but value "
                                         "in output is not expected.")
                if not (set_value_expected == set_value_of_cgroup):
                    raise error.TestFail("Run successful but value "
                                         "in cgroup is not expected.")
    else:
        if not status:
            raise error.TestFail("Run successfully with wrong command.")
