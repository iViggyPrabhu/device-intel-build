#!/usr/bin/env python

import sys
import json
import iniparser


# main Class to generate json file from ini configuration file
class FlashFileJson:

    def __init__(self, section, ip, variant):
        self.ip = ip
        self.flist = []
        self.flash = {'osplatform': 'android',
                      'parameters': {}, 'configurations': {},
                      'commands': [], 'groups': {}}
        self.gloption = {}
        self.preconditions = {}
        self.variant = variant
        self.section = section

    def add_file(self, longname, filename, shortname):
        if shortname in self.flash['parameters']:
            return
        fsection = 'file.' + filename
        if fsection in self.ip.sections():
            new = {'type': 'file',
                   'name': shortname,
                   'options': {}}

            for option in self.ip.options(fsection):
                value = self.ip.get(fsection, option)
                new['options'][option] = {'description': value,
                                          'value': value}
                self.flist.append(longname.rsplit(':')[0] + ':' + value)
        else:
            new = {'type': 'file',
                   'name': shortname,
                   'value': filename,
                   'description': filename}
            self.flist.append(longname)
        self.flash['parameters'][shortname] = new

    def parse_args(self, args, cmd_sec):
        for index, a in enumerate(args):
            if a.startswith('$'):
                longname = self.ip.get(cmd_sec, a[1:])
                filename = longname.split(':')[-1]
                shortname = filename.split('.')[0].lower()
                self.add_file(longname, filename, shortname)
                args[index] = '${' + shortname + '}'
        return args

    def group_default(self, group, c):
        cfg_sec = 'configuration.' + c
        if self.ip.has_option(cfg_sec, 'override-' + group):
            return self.ip.get(cfg_sec, 'override-' + group)
        if self.ip.has_option('group.' + group, 'default'):
            return self.ip.get('group.' + group, 'default')
        return False

    def add_group(self, group, c):
        conf = self.flash['configurations'][c]

        if 'groupsState' not in conf:
            conf['groupsState'] = {}

        conf['groupsState'][group] = self.group_default(group, c)

    def parse_global_cmd_option(self, opt):
        tool = opt[:-len('-command-options')]
        self.gloption[tool] = {}
        for parameter in self.ip.get(self.section, opt).split():
            p, v = parameter.split('=')
            self.gloption[tool][p] = self.ip.fix_type(v)

    def parse_precondition(self, precondition, tool):
        prec = {}
        section = 'precondition.' + precondition
        to_copy = ['description', 'expression', 'skipOnFailure' ]
        prec['section'] = self.ip.copy_option(section, to_copy)
        if self.ip.has_option(section, 'exception'):
            prec['exception'] = self.ip.get(section, 'exception')
        cmd_name = 'command.' + precondition
        if cmd_name in self.ip.seclist:
            to_copy = ['tool', 'description', 'variable', 'mandatory',
                       'group', 'defaultValue']
            cmd = self.ip.copy_option(cmd_name, to_copy)
            cmd = self.add_global_cmd_option(cmd)
            prec['cmd'] = cmd
            if 'group' in cmd:
                for config in self.ip.get(self.section, 'configurations').split():
                    self.add_group(cmd['group'], config)
        self.preconditions[tool] = prec

    def parse_global_cmd_precondition(self, opt):
        tool = opt[:-len('-command-preconditions')]
        for parameter in self.ip.get(self.section, opt).split():
            self.parse_precondition(parameter, tool)

    def parse_global_option(self):
        for opt in self.ip.options(self.section):
            if opt.endswith('-command-options'):
                self.parse_global_cmd_option(opt)
            elif opt.endswith('-command-preconditions'):
                self.parse_global_cmd_precondition(opt)
            else:
                continue

    def add_global_cmd_option(self, cmd):
        if cmd['tool'] in self.gloption:
            cmd = dict(self.gloption[cmd['tool']].items() + cmd.items())
        return cmd

    def add_global_cmd_precondition(self, cmd, cmd_set):
        if cmd['tool'] in self.preconditions:
            prec = self.preconditions[cmd['tool']]
            if 'exception' in prec and cmd_set == prec['exception']:
                return cmd
            cmd['precondition'] = prec['section']

            if 'cmd' in prec:
                new = prec['cmd'].copy()
                new['restrict'] = cmd['restrict']
                self.flash['commands'].append(new)

        return cmd

    def parse_cmd(self, cmd_set, configuration):

        for section, c in self.ip.sectionsfilter('command.' + cmd_set + '.'):
            if self.ip.has_option(section, 'variant'):
                if self.variant not in self.ip.get(section, 'variant').split():
                    continue
            to_copy = ['tool', 'description', 'mandatory', 'timeout',
                       'retry', 'duration', 'group', 'state']
            new = self.ip.copy_option(section, to_copy)
            if 'group' in new:
                self.add_group(new['group'], configuration)

            new['restrict'] = [configuration]
            if self.ip.has_option(section, 'arg'):
                args = self.ip.get(section, 'arg').split()
                args = self.parse_args(args, section)
                new['args'] = ' '.join(args)

            new = self.add_global_cmd_precondition(new, cmd_set)
            new = self.add_global_cmd_option(new)
            self.flash['commands'].append(new)

    def add_parameter(self, section, parameter=None):
        if self.ip.has_option(section, 'parameters'):
            parameters = self.ip.get(section, 'parameters')
            plist = [p.split(':') for p in parameters.split()]
            pdict = {f: p for f, p in plist}
            self.flash['configurations'][section.split('.')[1]]['parameters'] = pdict
        else:
            to_copy = ['name', 'type', 'description', 'filter', 'computedValue', 'value']
            new = self.ip.copy_option(section, to_copy)
            if self.ip.has_option(section, 'tool'):
                to_copy = ['description', 'tool']
                subcommand = self.ip.copy_option(section, to_copy)
                if self.ip.has_option(section, 'arg'):
                    subcommand['args'] = self.ip.get(section, 'arg')
                subcommand = self.add_global_cmd_option(subcommand)
                new['subCommand'] = subcommand
            self.flash['parameters'][parameter] = new

    def parse(self):
        for config in self.ip.get(self.section, 'configurations').split():
            section = 'configuration.' + config
            to_copy = ['startState', 'brief', 'description', 'default']

            self.flash['configurations'][config] = self.ip.copy_option(section, to_copy)
            self.flash['configurations'][config]['name'] = config

        self.parse_global_option()

        version = self.ip.get(self.section, 'version')
        self.flash['version'] = version

        for section, g in self.ip.sectionsfilter('group.'):
            to_copy = ['name', 'description']
            self.flash['groups'][g] = self.ip.copy_option(section, to_copy)

        for section, p in self.ip.sectionsfilter('parameter.'):
            self.add_parameter(section, p)

        for config in self.ip.get(self.section, 'configurations').split():
            section = 'configuration.' + config
            to_copy = ['startState', 'brief', 'description', 'default']

            for s in self.ip.get(section, 'sets').split():
                self.parse_cmd(s, config)
            if self.ip.has_option('configuration.' + config, 'parameters'):
                self.add_parameter('configuration.' + config)

    def files(self):
        return self.flist

    def finish(self):
        return json.dumps({'flash': self.flash}, indent=4, sort_keys=True)


# main Class to generate installer cmd file from ini configuration file
class FlashFileCmd:
    def __init__(self, section, ip, variant):
        self.ip = ip
        self.section = section
        self.variant = variant
        self.cmd = ""
        self.flist = []

    def parse_cmd(self, section, c):
        if self.ip.has_option(section, 'variant'):
            if self.variant not in self.ip.get(section, 'variant').split():
                return
        if not self.ip.has_option(section, 'tool'):
            return
        if self.ip.get(section, 'tool') != 'fastboot':
            return

        args = self.ip.get(section, 'arg').split()

        for index, a in enumerate(args):
            if a.startswith('$'):
                filename = self.ip.get(section, a[1:])
                self.flist.append(filename)
                filename = filename.split(':')[-1]
                args[index] = filename
        self.cmd += ' '.join(args) + '\n'

    def parse(self):
        for s in self.ip.get(self.section, 'sets').split():
            for section, c in self.ip.sectionsfilter('command.' + s + '.'):
                self.parse_cmd(section, c)

    def finish(self):
        return self.cmd

    def files(self):
        if self.ip.has_option(self.section, 'additional-files'):
            self.flist.extend(self.ip.get(self.section, 'additional-files').split())

        return self.flist


def parse_config(ip, variant, platform):
    results = []
    files = []

    if ip.has_option('global', 'additional-files'):
        files = ip.get('global', 'additional-files').split()

    for section, filename in ip.sectionsfilter('output.'):
        if ip.has_option(section, 'enable') and not ip.get(section, 'enable'):
            continue

        if filename.endswith('.json'):
            f = FlashFileJson(section, ip, variant)
        elif filename.endswith('.cmd'):
            f = FlashFileCmd(section, ip, variant)
        else:
            print "Warning, don't know how to generate", filename
            print "Please fix flashfiles.ini for this target"
            continue

        f.parse()
        results.append((filename, f.finish()))
        files.extend(f.files())

    flist = [f.rsplit(':', 1) for f in set(files)]
    return results, flist


def main():
    if len(sys.argv) != 4:
        print 'Usage : ', sys.argv[0], 'pft.ini target variant'
        print '    write json to stdout'
        sys.exit(1)

    file = sys.argv[1]
    target = sys.argv[2]
    variant = sys.argv[3]

    with open(file, 'r') as f:
        ip = iniparser.IniParser()
        ip.parse(f)

    results, files = parse_config(ip, variant, target)
    for fname, content in results:
        print fname
        print content
    print files

if __name__ == "__main__":
    main()
